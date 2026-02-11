const { spawn } = require('child_process');
const path = require('path');

const backendDir = __dirname;
process.chdir(backendDir);
console.log('Working directory:', process.cwd());

const python = spawn('python', ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'], {
  cwd: backendDir,
  stdio: 'inherit',
  shell: true
});

python.on('error', (err) => {
  console.error('Failed to start backend:', err);
});
