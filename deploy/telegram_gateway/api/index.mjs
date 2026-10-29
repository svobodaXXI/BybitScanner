import worker from "../worker.mjs";

export default async function handler(req, res) {
  const origin = "https://gateway.internal";
  const path = req.url || "/";
  const body = ["GET", "HEAD"].includes(req.method) ? undefined : await new Promise((resolve, reject) => {
    const chunks = [];
    let bytes = 0;
    req.on("data", chunk => {
      bytes += chunk.length;
      if (bytes > 2100000) { reject(new Error("request_too_large")); req.destroy(); }
      else chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
  const request = new Request(origin + path, {
    method: req.method, headers: req.headers, body
  });
  try {
    const response = await worker.fetch(request, process.env);
    res.status(response.status);
    for (const [key,value] of response.headers) {
      if (key === "content-type" || key === "cache-control") res.setHeader(key,value);
    }
    res.end(Buffer.from(await response.arrayBuffer()));
  } catch (_) {
    res.status(503).json({ok:false,error:"gateway_unavailable"});
  }
}
