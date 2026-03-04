import { createApp } from './app';

const args = process.argv.slice(2);
let host = 'localhost';
let port = 7900;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--host' && i + 1 < args.length) {
    host = args[i + 1];
    i++;
  } else if (args[i] === '--port' && i + 1 < args.length) {
    port = parseInt(args[i + 1], 10);
    i++;
  }
}

const app = createApp();

app.listen(port, host, () => {
  console.log(`talk-memory-server running at http://${host}:${port}`);
});
