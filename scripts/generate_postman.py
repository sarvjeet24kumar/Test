import json
import uuid
import os
from typing import Any, Dict, List

# We try to import the app to get the OpenAPI schema
try:
    import sys
    sys.path.append(os.getcwd())
    from app.main import app
    openapi_schema = app.openapi()
except Exception as e:
    print(f"Error loading app: {e}")
    # Fallback to an empty schema if app can't be loaded (e.g. environment issues)
    openapi_schema = {}

def create_postman_collection(schema: Dict[str, Any]) -> Dict[str, Any]:
    collection = {
        "info": {
            "name": schema.get("info", {}).get("title", "MiniMart API"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": schema.get("info", {}).get("description", ""),
        },
        "item": [],
        "variable": [
            {"key": "baseUrl", "value": "http://localhost:8000", "type": "string"},
            {"key": "token", "value": "", "type": "string"},
        ],
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]
        }
    }

    # Group by tags
    tag_groups: Dict[str, List[Dict[str, Any]]] = {}

    paths = schema.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            tags = details.get("tags", ["General"])
            tag = tags[0]
            if tag not in tag_groups:
                tag_groups[tag] = []
            
            # Postman item
            pm_item = {
                "name": details.get("summary", details.get("operationId", f"{method} {path}")),
                "request": {
                    "method": method.upper(),
                    "header": [],
                    "url": {
                        "raw": "{{baseUrl}}" + path.replace("{", ":").replace("}", ""),
                        "host": ["{{baseUrl}}"],
                        "path": path.strip("/").replace("{", ":").replace("}", "").split("/"),
                        "variable": []
                    },
                    "description": details.get("description", "")
                }
            }

            # Handle path variables
            for param in details.get("parameters", []):
                if param.get("in") == "path":
                    pm_item["request"]["url"]["variable"].append({
                        "key": param["name"],
                        "value": "",
                        "description": param.get("description", "")
                    })
                elif param.get("in") == "query":
                    if "query" not in pm_item["request"]["url"]:
                        pm_item["request"]["url"]["query"] = []
                    pm_item["request"]["url"]["query"].append({
                        "key": param["name"],
                        "value": None,
                        "description": param.get("description", ""),
                        "disabled": not param.get("required", False)
                    })

            # Handle request body
            request_body = details.get("requestBody", {})
            content = request_body.get("content", {})
            if "application/json" in content:
                pm_item["request"]["body"] = {
                    "mode": "raw",
                    "raw": "{\n  \n}",
                    "options": {"raw": {"language": "json"}}
                }

            tag_groups[tag].append(pm_item)

    # Convert tag groups to Postman folders
    for tag, items in tag_groups.items():
        collection["item"].append({
            "name": tag,
            "item": items
        })

    return collection

if openapi_schema:
    postman_coll = create_postman_collection(openapi_schema)
    output_path = "minimart_api_collection.json"
    with open(output_path, "w") as f:
        json.dump(postman_coll, f, indent=2)
    print(f"Postman collection generated at: {output_path}")
