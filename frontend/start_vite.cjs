const { spawn } = require('child_process');
const path = require('path');

process.chdir(__dirname);
console.log('Working directory:', process.cwd());

const vite = spawn('node', ['node_modules/vite/bin/vite.js', '--host', '--port', '5173'], {
  cwd: __dirname,
  stdio: 'inherit',
  shell: true
});

vite.on('error', (err) => {
  console.error('Failed to start vite:', err);
});
