import clsx from "clsx";
import Link from "@docusaurus/Link";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import Layout from "@theme/Layout";
import Heading from "@theme/Heading";
import styles from "./index.module.css";

const features = [
  {
    title: "Self-hosted",
    description:
      "Run on your own infrastructure. No data leaves your environment. Deploy with a single Docker command.",
  },
  {
    title: "Full-featured",
    description:
      "Collections, metadata filtering, hybrid search (RRF), recommendations, reranking, multi-key auth, Redis caching.",
  },
  {
    title: "Developer-first",
    description:
      "Python SDK, TypeScript SDK, CLI tool, OpenAPI spec, Prometheus metrics, OpenTelemetry tracing.",
  },
];

function Feature({ title, description }) {
  return (
    <div className={clsx("col col--4")}>
      <div className="text--center padding-horiz--md padding-vert--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

function HomepageHeader() {
  return (
    <header className={clsx("hero hero--primary", styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          VectorDB
        </Heading>
        <p className="hero__subtitle">
          Lightweight, self-hosted vector database for semantic search and AI
          applications
        </p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/quickstart"
          >
            Get Started in 5 minutes →
          </Link>
          <Link
            className="button button--outline button--secondary button--lg"
            to="/api-reference/overview"
            style={{ marginLeft: "1rem" }}
          >
            API Reference
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.title}
      description="Lightweight self-hosted vector database for AI applications"
    >
      <HomepageHeader />
      <main>
        <section className={styles.features}>
          <div className="container">
            <div className="row">
              {features.map((props, idx) => (
                <Feature key={idx} {...props} />
              ))}
            </div>
          </div>
        </section>

        <section className="container margin-vert--xl">
          <div className="row">
            <div className="col col--8 col--offset-2">
              <Heading as="h2">Start in 30 seconds</Heading>
              <pre>
                <code>{`docker compose up --build

curl -X POST http://localhost:8000/v1/collections \\
  -H "x-api-key: test-key" \\
  -d '{"name": "my-docs", "dim": 384, "distance_metric": "cosine"}'`}</code>
              </pre>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
