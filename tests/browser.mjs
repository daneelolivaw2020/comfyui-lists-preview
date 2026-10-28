import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile, readFile, unlink, stat, utimes } from "node:fs/promises";
const { chromium } = createRequire(import.meta.url)("playwright");
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "msedge", headless: true });
const page = await browser.newPage({viewport: {width: 1500, height: 1200}});
const errors = [];
page.on("pageerror", e => errors.push(e.message));
const checks = [];
const vue = process.env.VUE_NODES === "1";
if (vue) await page.route("**/api/settings", async route => {
    const response = await route.fetch();
    await route.fulfill({response, json: {...await response.json(), "Comfy.VueNodes.Enabled": true}});
});
async function check(name, fn) { await fn(); checks.push(name); console.log(`PASS ${name}`); }
async function widget(name, value) {
    return page.evaluate(({name, value}) => {
        const w = window.testNode.widgets.find(w => w.name === name);
        if (value !== undefined) { w.value = value; w.callback?.(value); }
        return w.value;
    }, {name, value});
}
async function queueAndFinish() {
    await page.evaluate(async () => {
        const {api} = await import("/scripts/api.js");
        const complete = new Promise(resolve => api.addEventListener("execution_success",resolve,{once:true}));
        await app.queuePrompt(0,1);
        await complete;
    });
}
async function observed() { return (await page.request.get("http://127.0.0.1:8189/qa/observed")).json(); }
const root = page.locator("section").filter({has: page.getByRole("heading", {name: "Visual list browser"})});
// Playwright pierces open shadow roots, just as the actual user interacts with them.
const cards = page.getByRole("button", {name: /^\d+ — /});
try {
    await page.goto(process.env.TEST_URL || "http://127.0.0.1:8189");
    await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{metadata:true,success_event:true,context:true,outcome:"success"}});
    await page.waitForFunction(() => window.app?.graph && window.LiteGraph?.registered_node_types?.LuisListPreview);
    await page.evaluate(() => {
        app.graph.clear();
        const n = LiteGraph.createNode("LuisListPreview");
        n.pos = [120, 150]; app.graph.add(n); window.testNode = n;
        app.canvas.ds.scale = 1; app.canvas.ds.offset = [0, 0];
    });
    await check("Loads all eight entries in the actual ComfyUI frontend", async () => {
        await cards.first().waitFor();
        assert.equal(await cards.count(), 8);
        assert.match(await widget("text"), /08 Stormy Coastline/);
        await page.waitForFunction(() => [...document.querySelectorAll("section")].some(e => e.shadowRoot?.querySelectorAll("img").length === 8));
        const fits = await cards.first().evaluate(card => card.querySelector(".label").getBoundingClientRect().bottom <= card.getBoundingClientRect().bottom + 1);
        assert.ok(fits, "Thumbnail title must fit inside the card in either renderer");
    });
    await check("Clicking a thumbnail synchronizes native row and dropdown", async () => {
        await page.getByRole("button", {name: "03 — Misty Mountain View", exact: true}).click();
        assert.equal(await widget("row"), 3);
        assert.equal(await page.getByRole("combobox", {name: "Select entry"}).inputValue(), "3");
        assert.equal(await page.getByRole("button", {name: "03 — Misty Mountain View", exact: true}).getAttribute("aria-pressed"), "true");
    });
    await check("Number selector and title toggle update the gallery output", async () => {
        await widget("row", 2);
        await widget("include_title", true);
        await page.waitForFunction(() => [...document.querySelectorAll("section")].some(e => e.shadowRoot?.querySelector(".output p")?.textContent.startsWith("Golden Window Light:")));
        assert.equal(await page.getByRole("combobox", {name: "Select entry"}).inputValue(), "2");
    });
    await check("Search filters thumbnails and preserves selection", async () => {
        await page.getByRole("searchbox", {name: "Search entries"}).fill("forest");
        assert.equal(await cards.count(), 1);
        assert.equal(await widget("row"), 2);
        await page.getByRole("searchbox", {name: "Search entries"}).fill("");
    });
    await check("Graph serialization/restoration keeps selection and title mode", async () => {
        await page.evaluate(async () => {
            const workflow = app.graph.serialize();
            window.savedWorkflow = workflow;
            await app.loadGraphData(workflow);
            window.testNode = app.graph._nodes.find(n => n.comfyClass === "LuisListPreview");
        });
        await page.getByRole("button", {name: "02 — Golden Window Light", exact: true}).waitFor();
        assert.equal(await widget("row"), 2);
        assert.equal(await widget("include_title"), true);
        assert.equal(await widget("source"), "File", "Restoring file text must not count as a user edit");
    });
    await check("Real queue submission receives backend output and advances increment mode", async () => {
        await widget("mode", "Increment after render");
        await widget("row", 8);
        await page.evaluate(() => app.queuePrompt(0, 1));
        await page.getByRole("status").filter({hasText:"Advances after successful render"}).waitFor();
        assert.equal(await widget("row"), 8, "Must retain row until downstream work succeeds");
        await page.waitForFunction(() => testNode.widgets.find(w => w.name === "row").value === 1);
        assert.match(await page.getByRole("status").filter({hasText: "Used row 8"}).innerText(), /Next: 1/);
    });
    await check("Text editing switches source and supports missing previews", async () => {
        await page.locator("textarea").fill("01 Custom One: Alpha\n02 Custom Two: Beta: detail");
        await widget("preview_folder", "absent-folder");
        await page.getByRole("button", {name: "02 — Custom Two", exact: true}).waitFor();
        assert.equal(await widget("source"), "Text");
        assert.equal(await page.getByText("No preview", {exact:true}).count(), 2);
        await page.getByRole("button", {name: "02 — Custom Two", exact:true}).click();
        await widget("include_title", false);
    });
    await check("Markup in list text is displayed safely", async () => {
        await widget("text", "01 <img src=x onerror=alert(1)>: Safe <script> text");
        await page.getByRole("button", {name: "01 — <img src=x onerror=alert(1)>", exact:true}).waitFor();
        assert.equal(await page.locator("script[src=x]").count(), 0);
        assert.equal(await cards.count(), 1);
    });
    await check("Refresh reloads files and recovers from a missing preview folder", async () => {
        await widget("source", "File");
        await widget("preview_folder", "");
        await page.getByRole("button", {name:"Reload files", exact:true}).click();
        await page.getByRole("button", {name: "08 — Stormy Coastline", exact:true}).waitFor();
        assert.equal(await cards.count(), 8);
    });
    await check("A connected STRING loads its own gallery and overrides the file", async () => {
        await widget("mode", "Fixed");
        await widget("row", 1);
        await page.evaluate(() => {
            const source = LiteGraph.createNode("TestListSource"); source.pos = [850,200];
            app.graph.add(source); source.widgets[0].value = "01 Linked First: Connected alpha\n02 Linked Second: Connected beta";
            source.connect(0, testNode, testNode.inputs.findIndex(i => i.name === "list_input"));
            window.testSource = source;
        });
        await page.getByRole("status").filter({hasText:"Connected list: run once"}).waitFor();
        await page.evaluate(() => app.queuePrompt(0, 1));
        await page.getByRole("button", {name:"02 — Linked Second", exact:true}).waitFor();
        assert.equal(await cards.count(), 2);
        await page.getByRole("button", {name:"02 — Linked Second", exact:true}).click();
        await page.evaluate(() => app.queuePrompt(0,1));
        await page.waitForFunction(() => [...document.querySelectorAll("section")].some(e => e.shadowRoot?.querySelector(".status")?.textContent.startsWith("Used row 2")));
        assert.match(await widget("text"), /Linked Second/);
        await page.evaluate(() => app.graph.remove(window.testSource));
        await page.getByRole("button", {name:"08 — Stormy Coastline", exact:true}).waitFor();
    });
    await check("Randomize selects a different next row after a successful run", async () => {
        await widget("mode", "Randomize");
        await widget("row", 1);
        await page.evaluate(() => app.queuePrompt(0,1));
        await page.waitForFunction(() => testNode.widgets.find(w=>w.name==="row").value !== 1);
        assert.ok((await widget("row")) >= 2);
    });
    await check("Three queued renders increment independently", async () => {
        await widget("mode", "Increment after render");
        await widget("row", 1);
        await page.evaluate(() => app.queuePrompt(0,3));
        await page.waitForFunction(() => testNode.widgets.find(w=>w.name==="row").value === 4);
        assert.match(await page.getByRole("status").filter({hasText:"Used row 3"}).innerText(), /Next: 4/);
    });
    await check("Increment works when workflow metadata is absent", async () => {
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{metadata:false}});
        await widget("row", 2);
        await page.evaluate(() => app.queuePrompt(0,1));
        await page.waitForFunction(() => testNode.widgets.find(w=>w.name==="row").value === 3, null, {timeout:4000});
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{metadata:true}});
    });
    await check("Increment waits for executing(null) on older completion protocols", async () => {
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{success_event:false,context:false}});
        await widget("row", 5);
        await page.evaluate(() => app.queuePrompt(0,1));
        await page.getByRole("status").filter({hasText:"Advances after successful render"}).waitFor();
        assert.equal(await widget("row"), 5);
        await page.waitForFunction(() => testNode.widgets.find(w=>w.name==="row").value === 6, null, {timeout:4000});
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{success_event:true,context:true}});
    });
    await check("Interrupted render preserves the row and the retry uses it again", async () => {
        await widget("row", 2);
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{outcome:"interrupted"}});
        await page.evaluate(() => app.queuePrompt(0,1));
        await page.getByRole("status").filter({hasText:"Render did not finish"}).waitFor();
        assert.equal(await widget("row"), 2);
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{outcome:"success"}});
        await page.evaluate(() => app.queuePrompt(0,1));
        await page.waitForFunction(() => testNode.widgets.find(w=>w.name==="row").value === 3, null, {timeout:4000});
        assert.match(await page.getByRole("status").filter({hasText:"Used row 2"}).innerText(), /Next: 3/);
    });
    await check("Manual row changes during render survive completion", async () => {
        await widget("row", 2);
        await page.evaluate(() => app.queuePrompt(0,1));
        await page.getByRole("status").filter({hasText:"Advances after successful render"}).waitFor();
        await page.getByRole("button", {name:"07 — Cozy Café Atmosphere", exact:true}).click();
        // Wait for the fixture's downstream completion, then check the user's choice.
        await page.waitForTimeout(650);
        assert.equal(await widget("row"), 7);
    });
    await check("Reload rescans edited text and added, replaced and deleted images", async () => {
        const base = new URL("../.test-runtime/library/", import.meta.url);
        const text = new URL("texts/reload.txt", base);
        const dir = new URL("previews/reload/", base);
        const one = new URL("01.png", dir), two = new URL("02.png", dir);
        await mkdir(dir, {recursive:true});
        for (const path of [one,two]) await unlink(path).catch(e=>{if(e.code!=="ENOENT")throw e;});
        try {
            await writeFile(text, "01 Reload One: First\n02 Reload Two: Second");
            await page.getByRole("button", {name:"Reload files",exact:true}).click();
            await page.waitForFunction(() => testNode.widgets.find(w=>w.name==="list_file").options.values.includes("reload.txt"));
            await widget("list_file", "reload.txt");
            await widget("row", 1);
            await page.getByRole("button", {name:"01 — Reload One",exact:true}).waitFor();
            assert.equal(await page.getByText("No preview",{exact:true}).count(),2);
            const fixture1 = await readFile(new URL("previews/illumination/01.png",base));
            const fixture2 = await readFile(new URL("previews/illumination/02.png",base));
            await writeFile(one,fixture1);
            await page.getByRole("button", {name:"Reload files",exact:true}).click();
            let image = page.getByRole("button", {name:"01 — Reload One",exact:true}).locator("img");
            await image.waitFor();
            await image.evaluate(img=>img.decode());
            const oldSrc = await image.getAttribute("src");
            const pixel = async locator => locator.evaluate(img=>{const c=document.createElement("canvas");c.width=1;c.height=1;const ctx=c.getContext("2d");ctx.drawImage(img,100,50,1,1,0,0,1,1);return [...ctx.getImageData(0,0,1,1).data];});
            const originalPixel = await pixel(image);
            const originalStat = await stat(one);
            await writeFile(one,fixture2);
            await utimes(one,originalStat.atime,originalStat.mtime);
            await writeFile(two,fixture1);
            await writeFile(text, "01 Reload One Updated: Changed\n02 Reload Two: Second");
            await page.getByRole("button", {name:"Reload files",exact:true}).click();
            image = page.getByRole("button", {name:"01 — Reload One Updated",exact:true}).locator("img");
            await image.waitFor(); await image.evaluate(img=>img.decode());
            assert.notEqual(await image.getAttribute("src"),oldSrc);
            assert.notDeepEqual(await pixel(image),originalPixel);
            assert.match(await widget("text"), /Updated: Changed/);
            assert.equal(await page.getByText("No preview",{exact:true}).count(),0);
            await unlink(one);
            await page.getByRole("button", {name:"Reload files",exact:true}).click();
            await page.getByText("No preview",{exact:true}).waitFor();
            await page.getByText("Library folders",{exact:true}).click();
            assert.match(await page.locator(".paths").innerText(),/previews[\\/]reload/);
        } finally {
            for (const path of [one,two,text]) await unlink(path).catch(e=>{if(e.code!=="ENOENT")throw e;});
            await widget("list_file","illumination.txt");
            await page.getByRole("button",{name:"Reload files",exact:true}).click();
            await page.getByRole("button",{name:"08 — Stormy Coastline",exact:true}).waitFor();
        }
    });
    await check("Approved outputs and affixes are delivered by the queued node", async () => {
        await widget("mode","Fixed"); await widget("row",3);
        const outputs = await page.evaluate(()=>testNode.outputs.map(o=>[o.name,o.type]));
        assert.deepEqual(outputs,[["text","STRING"],["list_file","STRING"],["row","INT"],["title","STRING"],["description","STRING"],["image","IMAGE"]]);
        await widget("prefix","photo, "); await widget("suffix",", soft grain");
        await widget("include_title",true);
        await queueAndFinish();
        const nodeId = String(await page.evaluate(()=>testNode.id));
        const result = (await observed()).filter(r=>r.node_id===nodeId).at(-1);
        assert.match(result.text,/^photo, Misty Mountain View: .*?, soft grain$/);
        assert.equal(result.title,"Misty Mountain View");
        assert.match(result.description,/^Diffused morning light/);
        assert.ok(!result.description.includes("photo, "));
        assert.match(result.list_file,/texts[\\/]illumination\.txt$/);
        assert.equal(result.row,3);
        assert.deepEqual(result.image_shape,[1,240,320,3]);
    });
    await check("The IMAGE output feeds a consumer directly from the custom preview directory", async () => {
        await page.evaluate(()=>{
            const image = LiteGraph.createNode("TestImageSink");image.pos=[850,200];app.graph.add(image);
            testNode.connect(5,image,0);window.testImageSink=image;
            const text = LiteGraph.createNode("TestTextSink");text.pos=[850,550];app.graph.add(text);
            testNode.connect(0,text,0);window.testTextSink=text;
        });
        await queueAndFinish();
        const result = (await observed()).filter(r=>r.sink).at(-1);
        assert.equal(result.skipped,false);
        assert.deepEqual(result.image_shape,[1,240,320,3]);
        assert.match((await observed()).filter(r=>r.text_sink).at(-1).value,/^photo, Misty Mountain View:/);
    });
    await check("Missing preview skips the image consumer while text and metadata still execute", async () => {
        await widget("preview_folder","missing-v02-preview");
        await widget("text","titleless text");
        await widget("row",1);
        await page.getByRole("button",{name:"01 — titleless text",exact:true}).waitFor();
        await queueAndFinish();
        const records = await observed();
        const result = records.filter(r=>r.node_id).at(-1);
        assert.equal(result.list_file,"file: none");
        assert.equal(result.title,"no title");
        assert.equal(result.description,"titleless text");
        assert.equal(result.text,"photo, titleless text, soft grain");
        assert.equal(records.filter(r=>r.sink).at(-1).skipped,true);
        assert.equal(records.filter(r=>r.text_sink).at(-1).value,result.text);
    });
    await check("Old single-output workflows gain new sockets without losing their text connection", async () => {
        await widget("source","File"); await widget("preview_folder","");
        await widget("prefix","");await widget("suffix","");await widget("include_title",false);
        await page.getByRole("button",{name:"08 — Stormy Coastline",exact:true}).waitFor();
        await page.evaluate(async()=>{
            app.graph.remove(window.testImageSink);
            const workflow=app.graph.serialize();
            const old=workflow.nodes.find(n=>n.type==="LuisListPreview");
            old.outputs=old.outputs.slice(0,1);
            old.widgets_values=old.widgets_values.slice(0,7);
            if(old.widgets_values_named){delete old.widgets_values_named.prefix;delete old.widgets_values_named.suffix;}
            old.inputs=old.inputs.filter(i=>!["prefix","suffix"].includes(i.name));
            await app.loadGraphData(workflow);
            window.testNode=app.graph._nodes.find(n=>n.comfyClass==="LuisListPreview");
            window.testTextSink=app.graph._nodes.find(n=>n.comfyClass==="TestTextSink");
        });
        await page.getByRole("button",{name:"03 — Misty Mountain View",exact:true}).waitFor();
        assert.equal(await page.evaluate(()=>testNode.outputs.length),6);
        assert.equal(await widget("source"),"File");
        assert.equal(await widget("prefix"),"");assert.equal(await widget("suffix"),"");
        assert.equal(await page.evaluate(()=>testNode.outputs[0].links.length),1);
        await queueAndFinish();
        assert.match((await observed()).filter(r=>r.text_sink).at(-1).value,/^Blue and magenta/);
        assert.match((await observed()).filter(r=>r.node_id).at(-1).list_file,/texts[\\/]illumination\.txt$/);
        await page.evaluate(()=>app.graph.remove(window.testTextSink));
    });
    await check("Restoring previously loaded text refreshes the gallery", async () => {
        await widget("source", "File"); await widget("row", 1); await widget("mode", "Fixed");
        await page.getByRole("button", {name:"08 — Stormy Coastline",exact:true}).waitFor();
        await queueAndFinish();
        const original = await widget("text");
        await widget("text", "01 Edited: Temporary description");
        await page.getByRole("button", {name:"01 — Edited",exact:true}).waitFor();
        await widget("text", original);
        await page.getByRole("button", {name:"08 — Stormy Coastline",exact:true}).waitFor();
        assert.equal(await widget("source"), "Text");
        assert.equal(await cards.count(), 8);
    });
    await check("Late execution results preserve text edits and their gallery", async () => {
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{node_delay:0.7}});
        try {
            await widget("source", "File"); await widget("row", 1);
            await page.getByRole("button", {name:"08 — Stormy Coastline",exact:true}).waitFor();
            await page.evaluate(async () => {
                const {api} = await import("/scripts/api.js");
                const started = new Promise(resolve => api.addEventListener("execution_start",resolve,{once:true}));
                window.reviewCompletion = new Promise(resolve => api.addEventListener("execution_success",resolve,{once:true}));
                await app.queuePrompt(0,1); await started;
            });
            await widget("text", "01 New Choice: My unsaved changes");
            await page.getByRole("button", {name:"01 — New Choice",exact:true}).waitFor();
            await page.evaluate(() => window.reviewCompletion);
            assert.equal(await widget("text"), "01 New Choice: My unsaved changes");
            assert.equal(await cards.count(), 1);
            assert.equal(await page.getByRole("button", {name:"01 — New Choice",exact:true}).count(), 1);
            assert.match((await observed()).filter(r=>r.node_id).at(-1).text, /^Blue and magenta/);
        } finally {
            await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{node_delay:0}});
        }
    });
    await check("Late execution results preserve a newly selected file and its gallery", async () => {
        const text = new URL("../.test-runtime/library/texts/review-other.txt", import.meta.url);
        await writeFile(text, "01 Other File: Keep this selection");
        await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{node_delay:0.7}});
        try {
            await widget("source", "File"); await widget("row",1);
            await page.getByRole("button", {name:"Reload files",exact:true}).click();
            await page.waitForFunction(() => testNode.widgets.find(w=>w.name==="list_file").options.values.includes("review-other.txt"));
            await page.getByRole("button", {name:"08 — Stormy Coastline",exact:true}).waitFor();
            await page.evaluate(async () => {
                const {api} = await import("/scripts/api.js");
                const started = new Promise(resolve => api.addEventListener("execution_start",resolve,{once:true}));
                window.reviewCompletion = new Promise(resolve => api.addEventListener("execution_success",resolve,{once:true}));
                await app.queuePrompt(0,1); await started;
            });
            await widget("list_file","review-other.txt");
            await page.getByRole("button", {name:"01 — Other File",exact:true}).waitFor();
            await page.evaluate(() => window.reviewCompletion);
            assert.equal(await widget("list_file"),"review-other.txt");
            assert.equal(await widget("text"),"01 Other File: Keep this selection");
            assert.equal(await page.getByRole("button", {name:"01 — Other File",exact:true}).count(),1);
        } finally {
            await unlink(text);
            await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{node_delay:0}});
            await widget("list_file","illumination.txt");
            await page.getByRole("button", {name:"Reload files",exact:true}).click();
            await page.getByRole("button", {name:"08 — Stormy Coastline",exact:true}).waitFor();
        }
    });
    await check("Manual choices made while queued survive with and without workflow metadata", async () => {
        await widget("source", "File"); await widget("mode", "Increment after render");
        await page.getByRole("button", {name:"08 — Stormy Coastline",exact:true}).waitFor();
        try {
            for (const metadata of [true, false]) {
                await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{start_delay:0.6,metadata}});
                await widget("row",1);
                await page.evaluate(async () => {
                    const {api} = await import("/scripts/api.js");
                    window.reviewCompletion = new Promise(resolve => api.addEventListener("execution_success",resolve,{once:true}));
                    await app.queuePrompt(0,1);
                });
                await widget("row",7);
                await page.evaluate(() => window.reviewCompletion);
                assert.equal(await widget("row"),7);
                assert.equal(await page.getByRole("button", {name:"07 — Cozy Café Atmosphere",exact:true}).getAttribute("aria-pressed"),"true");
                assert.equal((await observed()).filter(r=>r.node_id).at(-1).row,1);
            }
        } finally {
            await page.request.post("http://127.0.0.1:8189/qa/settings", {data:{start_delay:0.05,metadata:true}});
        }
    });
    await widget("mode", "Fixed"); await widget("row", 3);
    const workflow = await page.evaluate(() => app.graph.serialize());
    await mkdir("test-results", {recursive:true});
    await writeFile(`test-results/workflow${vue ? "-vue" : ""}.json`, JSON.stringify(workflow, null, 2));
    await page.evaluate(() => { app.canvas.ds.scale = 0.85; app.canvas.ds.offset = [0,0]; });
    await mkdir("test-results", {recursive:true});
    await page.screenshot({path:`test-results/comfyui-gallery${vue ? "-vue" : ""}.png`, fullPage:true});
    assert.deepEqual(errors, [], "No extension JavaScript errors");
    await writeFile(`test-results/browser-results${vue ? "-vue" : ""}.json`, JSON.stringify({frontend:"1.57.3", renderer:vue?"Nodes 2.0":"LiteGraph", checks, errors}, null, 2));
    console.log(`${checks.length} browser checks passed`);
} finally { await browser.close(); }
