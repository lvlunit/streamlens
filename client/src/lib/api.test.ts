import { buildUrl, insertClusterSchema } from "./api";

describe("buildUrl", () => {
  it("replaces a single param", () => {
    expect(buildUrl("/api/clusters/:id", { id: 1 })).toBe("/api/clusters/1");
  });

  it("replaces multiple params", () => {
    expect(buildUrl("/api/clusters/:id/schema/:subject", { id: 1, subject: "orders-value" }))
      .toBe("/api/clusters/1/schema/orders-value");
  });

  it("returns path unchanged when no params given", () => {
    expect(buildUrl("/api/clusters")).toBe("/api/clusters");
  });

  it("returns path unchanged when params don't match", () => {
    expect(buildUrl("/api/clusters/:id", { name: "test" })).toBe("/api/clusters/:id");
  });

  it("handles numeric values", () => {
    expect(buildUrl("/api/clusters/:id", { id: 42 })).toBe("/api/clusters/42");
  });
});

describe("insertClusterSchema", () => {
  it("validates a minimal valid cluster", () => {
    const result = insertClusterSchema.safeParse({
      name: "test",
      bootstrapServers: "localhost:9092",
    });
    expect(result.success).toBe(true);
  });

  it("rejects missing name", () => {
    const result = insertClusterSchema.safeParse({
      bootstrapServers: "localhost:9092",
    });
    expect(result.success).toBe(false);
  });

  it("rejects empty name", () => {
    const result = insertClusterSchema.safeParse({
      name: "",
      bootstrapServers: "localhost:9092",
    });
    expect(result.success).toBe(false);
  });

  it("rejects missing bootstrapServers", () => {
    const result = insertClusterSchema.safeParse({
      name: "test",
    });
    expect(result.success).toBe(false);
  });

  it("accepts optional fields", () => {
    const result = insertClusterSchema.safeParse({
      name: "test",
      bootstrapServers: "localhost:9092",
      schemaRegistryUrl: "http://localhost:8081",
      connectUrl: "http://localhost:8083",
      jmxHost: "localhost",
      jmxPort: 9999,
      enableKafkaEventProduceFromUi: true,
    });
    expect(result.success).toBe(true);
  });

  it("coerces jmxPort from empty string to undefined", () => {
    const result = insertClusterSchema.safeParse({
      name: "test",
      bootstrapServers: "localhost:9092",
      jmxPort: "",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.jmxPort).toBeUndefined();
    }
  });
});
