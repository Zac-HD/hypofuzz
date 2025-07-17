import simpleImportSort from "eslint-plugin-simple-import-sort";
import reactHooks from "eslint-plugin-react-hooks";
import tsParser from "@typescript-eslint/parser";

export default [{
    plugins: {
        "simple-import-sort": simpleImportSort,
        "react-hooks": reactHooks,
    },

    languageOptions: {
        parser: tsParser,
        ecmaVersion: "latest",
        sourceType: "module",
    },

    rules: {
        "simple-import-sort/imports": "error",
        "simple-import-sort/exports": "error",
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "error",
    },
}];
