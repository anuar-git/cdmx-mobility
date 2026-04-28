import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        cdmx: {
          green: "#16a34a",
          red: "#dc2626",
          amber: "#d97706",
          blue: "#2563eb",
          slate: "#0f172a",
        },
      },
    },
  },
  plugins: [],
};

export default config;
