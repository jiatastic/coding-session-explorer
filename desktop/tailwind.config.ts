import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Avenir Next", "Helvetica Neue", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
}

export default config
