/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server bundle (.next/standalone) so the Docker
  // runtime image only needs node + the traced dependencies.
  output: "standalone",
};

export default nextConfig;
