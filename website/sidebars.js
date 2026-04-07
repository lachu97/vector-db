// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    "introduction",
    "quickstart",
    {
      type: "category",
      label: "Core Concepts",
      collapsed: false,
      items: [
        "concepts/collections",
        "concepts/vectors",
        "concepts/distance-metrics",
        "concepts/hybrid-search",
      ],
    },
    {
      type: "category",
      label: "SDKs & CLI",
      collapsed: false,
      items: ["sdks/python", "sdks/typescript", "sdks/cli"],
    },
    {
      type: "category",
      label: "Deployment",
      items: ["deployment/docker", "deployment/configuration"],
    },
  ],
  api: [
    "api-reference/overview",
    "api-reference/authentication",
    {
      type: "category",
      label: "Collections",
      items: [
        "api-reference/collections/create",
        "api-reference/collections/list",
        "api-reference/collections/get",
        "api-reference/collections/delete",
      ],
    },
    {
      type: "category",
      label: "Vectors",
      items: [
        "api-reference/vectors/upsert",
        "api-reference/vectors/bulk-upsert",
        "api-reference/vectors/delete",
        "api-reference/vectors/delete-batch",
      ],
    },
    {
      type: "category",
      label: "Search",
      items: [
        "api-reference/search/search",
        "api-reference/search/recommend",
        "api-reference/search/similarity",
        "api-reference/search/rerank",
        "api-reference/search/hybrid-search",
      ],
    },
    {
      type: "category",
      label: "Admin",
      items: ["api-reference/admin/health", "api-reference/admin/keys"],
    },
  ],
};

export default sidebars;
