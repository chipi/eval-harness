"""A dataset record as Croissant 1.1 JSON-LD (PLAN_0.8.0 E6), so other tools read it.

What maps where:
  - the record: name (the id), description, version, license (an SPDX page), url (the source's), datePublished (made
    at), creator (given: a record has none), prov:wasDerivedFrom (the parent it was made from: Croissant 1.1 keeps provenance in PROV-O), the card as `rai:` properties;
  - distribution: the record file itself (a FileObject with its sha256) and the items' files (a FileSet of the items
    folder, or a FileObject per item fetched from an address, each with its sha256);
  - one RecordSet, `items`: per item its id and fields read from the record by jsonPath, its text from its file.
Nothing is invented: a required property the record cannot give (creator, url, license) is left out and named.
Checked against the spec's keys, not run through mlcroissant (not a dependency).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from evaluation_harness import _licences, _store

CONFORMS = "http://mlcommons.org/croissant/1.1"
#: The spec's context (Croissant 1.1, Appendix 1), as it gives it.
CONTEXT: dict[str, Any] = {
    "@language": "en",
    "@vocab": "http://schema.org/",
    "sc": "http://schema.org/",
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "dct": "http://purl.org/dc/terms/",
    "annotation": "cr:annotation",
    "arrayShape": "cr:arrayShape",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "containedIn": "cr:containedIn",
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "equivalentProperty": "cr:equivalentProperty",
    "excludes": "cr:excludes",
    "extract": "cr:extract",
    "field": "cr:field",
    "fileObject": "cr:fileObject",
    "fileProperty": "cr:fileProperty",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isArray": "cr:isArray",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "parentField": "cr:parentField",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "readLines": "cr:readLines",
    "sdVersion": "cr:sdVersion",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
    "unArchive": "cr:unArchive",
    "value": "cr:value",
}
REQUIRED = ("name", "description", "license", "url", "creator", "datePublished", "distribution")
#: A field set's types (_fields.TYPES) as schema.org data types; a duration is a number (its unit is the field's).
DATA_TYPES = {
    "text": "sc:Text",
    "number": "sc:Float",
    "integer": "sc:Integer",
    "boolean": "sc:Boolean",
    "date": "sc:Date",
    "datetime": "sc:DateTime",
    "duration": "sc:Float",
    "url": "sc:URL",
    "choice": "sc:Text",
}


def export(
    record: dict[str, Any],
    record_file: Path,
    items_dir: str,
    field_types: dict[str, str],
    creator: str | None,
) -> tuple[dict[str, Any], list[str]]:
    """(the Croissant document, the required properties it lacks)."""
    did = record["dataset_id"]
    src = record.get("source") or {}
    doc: dict[str, Any] = {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "conformsTo": CONFORMS,
        "name": did,
        "description": record.get("description") or "",
        "version": record.get("version"),
        "datePublished": record.get("created_at"),
    }
    lic = record.get("licence")
    if lic and _licences.url(lic):
        doc["license"] = _licences.url(lic)
    elif lic and lic != _licences.UNKNOWN:
        doc["license"] = lic
    if src.get("url"):
        doc["url"] = src["url"]
    if creator:
        doc["creator"] = {"@type": "sc:Person", "name": creator}
    parent = (record.get("derived_from") or {}).get("dataset_id") or (record.get("split") or {}).get("from")
    if parent:
        doc["@context"] = {**CONTEXT, "prov": "http://www.w3.org/ns/prov#"}
        doc["prov:wasDerivedFrom"] = {"@id": parent}
    for k, v in (record.get("card") or {}).items():
        doc[f"rai:{k}"] = v
    rec_id = f"{did}.json"
    dist: list[dict[str, Any]] = [
        {
            "@type": "cr:FileObject",
            "@id": rec_id,
            "name": rec_id,
            "contentUrl": f"data/datasets/{rec_id}",
            "encodingFormat": "application/json",
            "sha256": hashlib.sha256(_store.read_bytes(record_file)).hexdigest(),
        }
    ]
    items = record.get("items") or []
    fetched = [it for it in items if it.get("source_url")]
    local = [it for it in items if not it.get("source_url")]
    if local:
        dist.append(
            {
                "@type": "cr:FileSet",
                "@id": "items-files",
                "name": "items-files",
                "encodingFormat": "text/plain",
                "includes": f"{items_dir}/*",
            }
        )
    for it in fetched:
        dist.append(
            {
                "@type": "cr:FileObject",
                "@id": f"item-{it['item_id']}",
                "name": it["item_id"],
                "contentUrl": it["source_url"],
                "encodingFormat": "text/plain",
                "sha256": it["source_sha256"],
            }
        )
    doc["distribution"] = dist

    def field(name: str, data_type: str, source: dict[str, Any], description: str = "") -> dict[str, Any]:
        f: dict[str, Any] = {
            "@type": "cr:Field",
            "@id": f"items/{name}",
            "name": name,
            "dataType": data_type,
            "source": source,
        }
        if description:
            f["description"] = description
        return f

    fields = [
        field(
            "item_id",
            "sc:Text",
            {"fileObject": {"@id": rec_id}, "extract": {"jsonPath": "$.items[*].item_id"}},
            "the item's id, its identity with its sha256",
        ),
        field(
            "source_sha256",
            "sc:Text",
            {"fileObject": {"@id": rec_id}, "extract": {"jsonPath": "$.items[*].source_sha256"}},
        ),
    ]
    if local:
        fields.append(
            field(
                "text",
                "sc:Text",
                {"fileSet": {"@id": "items-files"}, "extract": {"fileProperty": "content"}},
                "the item's content",
            )
        )
    for name, t in field_types.items():
        fields.append(
            field(
                f"field_{name}",
                DATA_TYPES.get(str(t), "sc:Text"),
                {"fileObject": {"@id": rec_id}, "extract": {"jsonPath": f"$.items[*].fields.{name}"}},
            )
        )
    doc["recordSet"] = [
        {
            "@type": "cr:RecordSet",
            "@id": "items",
            "name": "items",
            "key": {"@id": "items/item_id"},
            "field": fields,
        }
    ]
    missing = [k for k in REQUIRED if not doc.get(k)]
    return doc, missing
