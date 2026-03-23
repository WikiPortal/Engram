/** @type {import('next').NextConfig} */
const path = require("path");
const fs   = require("fs");
const dotenv = require("dotenv");

const rootEnv = path.resolve(__dirname, "../.env");
if (fs.existsSync(rootEnv)) {
  const parsed = dotenv.parse(fs.readFileSync(rootEnv));
  for (const [k, v] of Object.entries(parsed)) {
    if (!process.env[k]) process.env[k] = v;
  }
}

const nextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};

module.exports = nextConfig;
