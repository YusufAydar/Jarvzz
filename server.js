// Jarvzz – kleiner Server ohne Abhängigkeiten (Node 18+)
// Start:  ANTHROPIC_API_KEY=sk-ant-... node server.js
// Dann im Browser (Chrome/Edge) öffnen: http://localhost:3000

const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = process.env.PORT || 3000;
const MODEL = process.env.JARVZZ_MODEL || "claude-sonnet-5-5";
const API_KEY = process.env.ANTHROPIC_API_KEY;
const PUBLIC = path.join(__dirname, "public");

const SYSTEM = `Du bist JARVZZ, ein persönlicher KI-Assistent im Stil von J.A.R.V.I.S.
Du sprichst Deutsch, bist höflich, trocken-humorvoll und sprichst den Nutzer mit "Sir" an.
Deine Antworten werden laut vorgelesen: antworte kurz (meist 1–3 Sätze), ohne Markdown,
ohne Aufzählungszeichen und ohne Emojis. Aktuelles Datum/Uhrzeit: {{NOW}}.`;

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };

async function chat(messages) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 400,
      system: SYSTEM.replace("{{NOW}}", new Date().toLocaleString("de-DE")),
      messages: messages.slice(-20),
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || `API-Fehler ${res.status}`);
  return data.content.filter((b) => b.type === "text").map((b) => b.text).join("\n");
}

http
  .createServer(async (req, res) => {
    if (req.method === "POST" && req.url === "/api/chat") {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", async () => {
        res.setHeader("content-type", "application/json");
        if (!API_KEY) {
          res.end(JSON.stringify({ reply: "Sir, mir fehlt noch der API-Schlüssel. Bitte starten Sie den Server mit ANTHROPIC_API_KEY." }));
          return;
        }
        try {
          const { messages } = JSON.parse(body);
          res.end(JSON.stringify({ reply: await chat(messages) }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ reply: "Sir, es gab ein Problem: " + e.message }));
        }
      });
      return;
    }
    const file = path.join(PUBLIC, req.url === "/" ? "index.html" : path.normalize(req.url).replace(/^(\.\.[\/\\])+/, ""));
    if (!file.startsWith(PUBLIC) || !fs.existsSync(file)) {
      res.statusCode = 404;
      return res.end("Not found");
    }
    res.setHeader("content-type", TYPES[path.extname(file)] || "application/octet-stream");
    fs.createReadStream(file).pipe(res);
  })
  .listen(PORT, () => console.log(`JARVZZ online → http://localhost:${PORT}  (Modell: ${MODEL})`));
