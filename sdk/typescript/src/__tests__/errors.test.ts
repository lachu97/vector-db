import {
  VectorDBError,
  NotFoundError,
  AlreadyExistsError,
  DimensionMismatchError,
  AuthenticationError,
  RateLimitError,
  ValidationError,
} from "../errors.js";

describe("Error hierarchy", () => {
  test("all errors extend VectorDBError", () => {
    expect(new NotFoundError("x")).toBeInstanceOf(VectorDBError);
    expect(new AlreadyExistsError("x")).toBeInstanceOf(VectorDBError);
    expect(new DimensionMismatchError("x")).toBeInstanceOf(VectorDBError);
    expect(new AuthenticationError("x")).toBeInstanceOf(VectorDBError);
    expect(new RateLimitError("x")).toBeInstanceOf(VectorDBError);
    expect(new ValidationError("x")).toBeInstanceOf(VectorDBError);
  });

  test("errors carry statusCode", () => {
    expect(new NotFoundError("x", 404).statusCode).toBe(404);
    expect(new AlreadyExistsError("x", 409).statusCode).toBe(409);
    expect(new AuthenticationError("x", 401).statusCode).toBe(401);
  });

  test("errors have correct name", () => {
    expect(new NotFoundError("x").name).toBe("NotFoundError");
    expect(new AlreadyExistsError("x").name).toBe("AlreadyExistsError");
    expect(new DimensionMismatchError("x").name).toBe("DimensionMismatchError");
    expect(new AuthenticationError("x").name).toBe("AuthenticationError");
    expect(new RateLimitError("x").name).toBe("RateLimitError");
    expect(new ValidationError("x").name).toBe("ValidationError");
  });

  test("instanceof works after setPrototypeOf", () => {
    const err = new NotFoundError("not found");
    expect(err instanceof NotFoundError).toBe(true);
    expect(err instanceof VectorDBError).toBe(true);
    expect(err instanceof Error).toBe(true);
  });
});
