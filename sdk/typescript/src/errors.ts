/**
 * VectorDB SDK error types.
 */

export class VectorDBError extends Error {
  readonly statusCode: number | undefined;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "VectorDBError";
    this.statusCode = statusCode;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class NotFoundError extends VectorDBError {
  constructor(message: string, statusCode = 404) {
    super(message, statusCode);
    this.name = "NotFoundError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class AlreadyExistsError extends VectorDBError {
  constructor(message: string, statusCode = 409) {
    super(message, statusCode);
    this.name = "AlreadyExistsError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class DimensionMismatchError extends VectorDBError {
  constructor(message: string, statusCode = 400) {
    super(message, statusCode);
    this.name = "DimensionMismatchError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class AuthenticationError extends VectorDBError {
  constructor(message: string, statusCode = 401) {
    super(message, statusCode);
    this.name = "AuthenticationError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class RateLimitError extends VectorDBError {
  constructor(message: string, statusCode = 429) {
    super(message, statusCode);
    this.name = "RateLimitError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ValidationError extends VectorDBError {
  constructor(message: string, statusCode = 422) {
    super(message, statusCode);
    this.name = "ValidationError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
