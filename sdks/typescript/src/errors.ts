/**
 * Canonical SDK Errors.
 */

export class ThinkumentError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ThinkumentError';
  }
}

export class CloudServiceRequiredError extends ThinkumentError {
  constructor(message: string = 'Operation requires Sovereign Cloud Thinkument service and an API key') {
    super(message);
    this.name = 'CloudServiceRequiredError';
  }
}

export class ConcurrencyConflictError extends ThinkumentError {
  constructor(message: string = 'Dispatch rejected due to concurrent state update or stale cursor') {
    super(message);
    this.name = 'ConcurrencyConflictError';
  }
}
