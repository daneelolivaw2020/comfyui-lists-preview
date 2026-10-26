"""Private ComfyUI list browser. No registration with a public registry."""
from .node import ListPreview
from .routes import register_routes

NODE_CLASS_MAPPINGS = {"LuisListPreview": ListPreview}
NODE_DISPLAY_NAME_MAPPINGS = {"LuisListPreview": "List Preview • Luis"}
WEB_DIRECTORY = "./web"

register_routes()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
