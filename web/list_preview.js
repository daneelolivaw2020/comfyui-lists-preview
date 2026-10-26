import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { attachBrowser } from "./list_browser.js?v=0.2.0";

app.registerExtension({
    name: "Luis.ListPreview",
    nodeCreated(node) {
        if (node.comfyClass === "LuisListPreview") attachBrowser(node, api);
    },
});
