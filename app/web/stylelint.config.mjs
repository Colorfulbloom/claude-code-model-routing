/** @type {import("stylelint").Config} */
export default {
  extends: ["stylelint-config-standard"],
  ignoreFiles: ["src/styles/tokens.css", "dist/**", "dist-sheet/**"],
  rules: {
    "color-no-hex": true,
  },
};
