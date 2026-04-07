// @ts-check
import { themes as prismThemes } from "prism-react-renderer";

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: "VectorDB",
  tagline: "Lightweight self-hosted vector database for AI applications",
  favicon: "img/favicon.ico",

  url: "https://lachu97.github.io",
  baseUrl: "/vector-db/",

  organizationName: "lachu97",
  projectName: "vector-db",
  deploymentBranch: "gh-pages",
  trailingSlash: false,

  onBrokenLinks: "warn",
  onBrokenMarkdownLinks: "warn",

  i18n: {
    defaultLocale: "en",
    locales: ["en"],
  },

  presets: [
    [
      "classic",
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: "./sidebars.js",
          routeBasePath: "/",
          editUrl: "https://github.com/lachu97/vector-db/edit/main/website/",
        },
        blog: false,
        theme: {
          customCss: "./src/css/custom.css",
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: {
        defaultMode: "dark",
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: "VectorDB",
        items: [
          {
            type: "docSidebar",
            sidebarId: "docs",
            position: "left",
            label: "Docs",
          },
          {
            type: "docSidebar",
            sidebarId: "api",
            position: "left",
            label: "API Reference",
          },
          {
            href: "https://github.com/lachu97/vector-db",
            label: "GitHub",
            position: "right",
          },
        ],
      },
      footer: {
        style: "dark",
        links: [
          {
            title: "Docs",
            items: [
              { label: "Quickstart", to: "/quickstart" },
              { label: "Python SDK", to: "/sdks/python" },
              { label: "TypeScript SDK", to: "/sdks/typescript" },
              { label: "CLI", to: "/sdks/cli" },
            ],
          },
          {
            title: "More",
            items: [
              {
                label: "GitHub",
                href: "https://github.com/lachu97/vector-db",
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} VectorDB.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ["python", "typescript", "bash", "json", "yaml"],
      },
    }),
};

export default config;
