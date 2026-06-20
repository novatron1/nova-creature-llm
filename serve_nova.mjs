import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 3000;

// Serve the standalone HTML file
const html = fs.readFileSync(path.join(__dirname, 'nova_standalone.html'), 'utf-8');

const server = http.createServer((req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Cache-Control': 'no-cache'
  });
  res.end(html);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`NOVA CREATURE WEB UI`);
  console.log(`URL: http://0.0.0.0:${PORT}`);
  console.log(`PID: ${process.pid}`);
});

// Keep alive
process.on('SIGTERM', () => { server.close(); process.exit(0); });
process.on('SIGINT', () => { server.close(); process.exit(0); });
