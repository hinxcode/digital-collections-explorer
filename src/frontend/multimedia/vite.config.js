import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let apiHost;
let apiPort;

try {
  const configPath = path.resolve(__dirname, '../../..', 'config.json');
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

  if (config.api_config) {
    apiHost = config.api_config.host === '0.0.0.0' ? 'localhost' : config.api_config.host;
    apiPort = config.api_config.port;
  }
} catch (error) {
  console.warn('Could not read config.json, using default API settings:', error);
}

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const isProduction = command === 'build';

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
        },
        '/images': {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
        },
        '/static': {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
        },
        '/media': {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
        }
      }
    },
    define: {
      'import.meta.env.API_BASE_URL': isProduction
        ? JSON.stringify('')
        : JSON.stringify(`http://${apiHost}:${apiPort}`)
    }
  }
});
