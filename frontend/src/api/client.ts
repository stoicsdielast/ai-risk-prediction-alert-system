const configuredApiUrl = import.meta.env.VITE_API_URL?.trim()

export const API_BASE_URL = (
  configuredApiUrl || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

interface ValidationIssue {
  loc?: Array<string | number>
  msg?: string
}

interface ErrorPayload {
  detail?: string | ValidationIssue[]
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function validationMessage(issues: ValidationIssue[]): string {
  const messages = issues
    .map((issue) => {
      const field = issue.loc?.at(-1)
      if (!issue.msg) return null
      return field ? `${String(field)}: ${issue.msg}` : issue.msg
    })
    .filter((message): message is string => Boolean(message))

  return messages.length > 0 ? messages.join('. ') : 'Please check your details.'
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let payload: ErrorPayload | null = null

  try {
    payload = (await response.json()) as ErrorPayload
  } catch {
    // The generic fallback below is safer than exposing an unexpected body.
  }

  const detail = payload?.detail
  const message = Array.isArray(detail)
    ? validationMessage(detail)
    : detail || 'Something went wrong. Please try again.'

  return new ApiError(response.status, message)
}

interface RequestOptions extends RequestInit {
  token?: string
}

export async function apiRequest<T>(
  path: string,
  { token, headers, ...options }: RequestOptions = {},
): Promise<T> {
  const requestHeaders = new Headers(headers)
  requestHeaders.set('Accept', 'application/json')

  if (options.body) {
    requestHeaders.set('Content-Type', 'application/json')
  }

  if (token) {
    requestHeaders.set('Authorization', `Bearer ${token}`)
  }

  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: requestHeaders,
    })
  } catch {
    throw new ApiError(
      0,
      'Cannot reach the server. Check that the backend is running and try again.',
    )
  }

  if (!response.ok) {
    throw await errorFromResponse(response)
  }

  return response.status === 204 ? undefined as T : (await response.json()) as T
}
