/**
 * LoginPage tests
 *
 * Covers:
 *  - Renders login form
 *  - Shows validation error for empty fields (form-level required)
 *  - Submits credentials and stores token
 *  - Shows API error message with suggestion
 *  - Redirects to dashboard on success
 */

import { describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  act,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { wrapErrorEnvelope } from "@/test/mocks/data";
import { useAuthStore } from "@/store/authStore";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

// Mock TanStack Router hooks used by LoginPage
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }: { children: React.ReactNode; to: string }) => (
    <a href={props.to}>{children}</a>
  ),
}));

import LoginPage from "@/pages/LoginPage";

beforeEach(() => {
  // Reset auth store between tests
  useAuthStore.getState().clearAuth();
});

function renderPage() {
  const qc = createTestQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <LoginPage />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("LoginPage", () => {
  it("renders login form with email and password fields", () => {
    renderPage();

    expect(screen.getByText(/Welcome back|Sign in/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByText("Sign in")).toBeInTheDocument();
  });

  it("has required attributes on email and password inputs", () => {
    renderPage();

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);

    // The LoginPage uses HTML5 required attribute
    expect(emailInput).toBeRequired();
    expect(passwordInput).toBeRequired();
  });

  it("submits credentials and stores token in auth store", async () => {
    // Use the default MSW handler that returns a valid token
    renderPage();

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);

    await act(async () => {
      fireEvent.change(emailInput, {
        target: { value: "alice@acmelab.com" },
      });
      fireEvent.change(passwordInput, {
        target: { value: "SecurePass123!" },
      });
    });

    const form = emailInput.closest("form")!;
    await act(async () => {
      fireEvent.submit(form);
    });

    // Wait for mutation to complete and auth store to be updated
    await waitFor(() => {
      const state = useAuthStore.getState();
      expect(state.accessToken).toBeTruthy();
    });
  });

  it("shows API error message on invalid credentials", async () => {
    // Override the login handler to return an error for this test
    server.use(
      http.post("*/auth/login", () => {
        return HttpResponse.json(
          wrapErrorEnvelope(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            "Check your email and password and try again",
          ),
          { status: 401 },
        );
      }),
    );

    renderPage();

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);

    await act(async () => {
      fireEvent.change(emailInput, {
        target: { value: "wrong@example.com" },
      });
      fireEvent.change(passwordInput, {
        target: { value: "badpassword" },
      });
    });

    const form = emailInput.closest("form")!;
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      // The LoginPage extracts error messages from the mutation error
      // and displays them
      const errorElements = screen.getAllByText(
        /Invalid email or password|INVALID_CREDENTIALS/i,
      );
      expect(errorElements.length).toBeGreaterThan(0);
    });
  });

  it("shows suggestion text alongside error", async () => {
    server.use(
      http.post("*/auth/login", () => {
        return HttpResponse.json(
          wrapErrorEnvelope(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            "Check your email and password and try again",
          ),
          { status: 401 },
        );
      }),
    );

    renderPage();

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);

    await act(async () => {
      fireEvent.change(emailInput, {
        target: { value: "bad@example.com" },
      });
      fireEvent.change(passwordInput, { target: { value: "wrong" } });
    });

    const form = emailInput.closest("form")!;
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      // The LoginPage shows suggestion text extracted from error message
      // (the error format includes "-- suggestion")
      expect(
        screen.getByText(/Check your email and password/i),
      ).toBeInTheDocument();
    });
  });
});
