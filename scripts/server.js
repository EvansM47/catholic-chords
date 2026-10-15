const http = require('http');
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');
const port = Number(process.env.PORT || 4173);
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8', '.webmanifest':'application/manifest+json; charset=utf-8', '.txt':'text/plain; charset=utf-8', '.db':'application/octet-stream', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.svg':'image/svg+xml' };
http.createServer((req,res)=>{
  const url = decodeURIComponent(req.url.split('?')[0]);
  const target = path.normalize(path.join(root, url === '/' ? 'index.html' : url));
  if (!target.startsWith(root)) { res.writeHead(403); return res.end('Forbidden'); }
  fs.stat(target,(err,stat)=>{
    if (err || !stat.isFile()) { res.writeHead(404); return res.end('Not found'); }
    res.writeHead(200, {'Content-Type': types[path.extname(target)] || 'application/octet-stream', 'Cache-Control':'no-cache'});
    fs.createReadStream(target).pipe(res);
  });
}).listen(port,()=>console.log(`Choir Hymns running at http://localhost:${port}`));
