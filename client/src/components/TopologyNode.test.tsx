import { render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "reactflow";
import TopologyNode from "./TopologyNode";

vi.mock("wouter", () => ({
  useRoute: () => [true, { id: "1" }],
}));

function renderNode(data: Record<string, unknown>, selected = false) {
  return render(
    <ReactFlowProvider>
      <TopologyNode data={data} selected={selected} />
    </ReactFlowProvider>
  );
}

describe("TopologyNode", () => {
  describe("topic node", () => {
    it("renders the topic label", () => {
      renderNode({ type: "topic", label: "orders" });
      expect(screen.getByText("orders")).toBeInTheDocument();
    });

    it("renders the TOPIC type label", () => {
      renderNode({ type: "topic", label: "orders" });
      expect(screen.getByText("Topic")).toBeInTheDocument();
    });
  });

  describe("consumer node", () => {
    it("renders the consumer label", () => {
      renderNode({ type: "consumer", label: "my-consumer-group", source: "auto-discovered" });
      expect(screen.getByText("my-consumer-group")).toBeInTheDocument();
    });

    it("shows Live badge for auto-discovered source", () => {
      renderNode({ type: "consumer", label: "cg", source: "auto-discovered" });
      expect(screen.getByText("Live")).toBeInTheDocument();
    });
  });

  describe("producer node", () => {
    it("renders the producer label", () => {
      renderNode({ type: "producer", label: "my-producer", source: "jmx" });
      expect(screen.getByText("my-producer")).toBeInTheDocument();
    });

    it("shows JMX badge", () => {
      renderNode({ type: "producer", label: "p", source: "jmx" });
      expect(screen.getByText("JMX")).toBeInTheDocument();
    });
  });

  describe("schema node", () => {
    it("renders single subject as label", () => {
      renderNode({
        type: "schema",
        label: "orders-value",
        subLabel: "AVRO",
        schemaType: "AVRO",
        subjects: ["orders-value"],
        subject: "orders-value",
        version: 1,
      });
      expect(screen.getByText("orders-value")).toBeInTheDocument();
      expect(screen.getByText("AVRO")).toBeInTheDocument();
    });

    it("renders Multiple subjects for grouped schemas", () => {
      renderNode({
        type: "schema",
        label: "Multiple subjects",
        subLabel: "AVRO · 2 subject(s)",
        schemaType: "AVRO",
        subjects: ["orders-value", "payments-value"],
        subject: "orders-value",
        version: 1,
        schemaId: 42,
      });
      expect(screen.getByText("Multiple subjects")).toBeInTheDocument();
      expect(screen.getByText("AVRO · 2 subject(s)")).toBeInTheDocument();
    });

    it("renders the SCHEMA type label", () => {
      renderNode({
        type: "schema",
        label: "orders-value",
        subjects: ["orders-value"],
        subject: "orders-value",
        version: 1,
      });
      expect(screen.getByText("Schema")).toBeInTheDocument();
    });
  });

  describe("connector node", () => {
    it("renders the connector label", () => {
      renderNode({ type: "connector", label: "my-sink-connector" });
      expect(screen.getByText("my-sink-connector")).toBeInTheDocument();
    });
  });

  describe("acl node", () => {
    it("renders the ACL label", () => {
      renderNode({
        type: "acl",
        label: "ACL (3)",
        topic: "orders",
        acls: [
          { principal: "User:alice", host: "*", operation: "READ", permissionType: "ALLOW" },
          { principal: "User:bob", host: "*", operation: "WRITE", permissionType: "ALLOW" },
          { principal: "User:carol", host: "*", operation: "DESCRIBE", permissionType: "ALLOW" },
        ],
      });
      expect(screen.getByText("ACL (3)")).toBeInTheDocument();
    });
  });

  describe("visual states", () => {
    it("applies highlight class when highlighted", () => {
      const { container } = renderNode({ type: "topic", label: "t", highlighted: true });
      const node = container.querySelector("[class*='scale-105']");
      expect(node).not.toBeNull();
    });

    it("applies search highlight class", () => {
      const { container } = renderNode({ type: "topic", label: "t", searchHighlighted: true });
      const node = container.querySelector("[class*='ring-yellow-500']");
      expect(node).not.toBeNull();
    });
  });
});
