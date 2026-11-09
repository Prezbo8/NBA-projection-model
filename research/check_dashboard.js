// Runs docs/index.html's script under node with a stub DOM: catches JS errors and prints what each tab renders.
const fs = require("fs");
const html = fs.readFileSync("docs/index.html", "utf8");
const js = html.slice(html.lastIndexOf("<script>") + 8, html.lastIndexOf("</script>"));
const els = {};
const el = id => els[id] ||= {id, innerHTML: "", textContent: "", hidden: false, onclick: null,
  classList: {toggle() {}}, dataset: {}, addEventListener() {}, querySelectorAll: () => [], value: ""};
global.document = {getElementById: el, querySelectorAll: () => [], querySelector: () => el("q"), addEventListener() {}};
global.window = global; global.localStorage = {getItem: () => null, setItem() {}};
eval(js);
const tail = el("paper").innerHTML; const k = tail.indexOf("Every game"); console.log("EVERY GAME: " + (k < 0 ? "MISSING" : tail.slice(k).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").slice(0, 1400)));
for (const id of ["stats", "games", "tomorrow", "paper"]) {
  const h = el(id).innerHTML;
  console.log(`#${id}: ${h.length} chars | ` + h.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").slice(0, 900));
}
