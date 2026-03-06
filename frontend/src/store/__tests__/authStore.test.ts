import { describe, it, expect, beforeEach } from "vitest";
import {
  useAuthStore,
  selectAccessToken,
  selectUser,
  selectIsAuthenticated,
  selectIsRefreshing,
  selectIsInitialized,
} from "../authStore";
import type { UserProfile } from "../authStore";

const mockUser: UserProfile = {
  id: "user-1",
  email: "scientist@lablink.io",
  name: "Ada Lovelace",
  role: "scientist",
  labId: "lab-abc",
};

beforeEach(() => {
  useAuthStore.setState({
    accessToken: null,
    user: null,
    isRefreshing: false,
    isInitialized: false,
  });
});

describe("authStore — initial state", () => {
  it("has null accessToken", () => {
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("has null user", () => {
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("is not refreshing", () => {
    expect(useAuthStore.getState().isRefreshing).toBe(false);
  });

  it("is not initialized", () => {
    expect(useAuthStore.getState().isInitialized).toBe(false);
  });
});

describe("authStore — setAuth", () => {
  it("stores token and user", () => {
    useAuthStore.getState().setAuth("tok.e.n", mockUser);
    expect(useAuthStore.getState().accessToken).toBe("tok.e.n");
    expect(useAuthStore.getState().user).toEqual(mockUser);
  });
});

describe("authStore — clearAuth", () => {
  it("clears token and user", () => {
    useAuthStore.getState().setAuth("tok.e.n", mockUser);
    useAuthStore.getState().clearAuth();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });
});

describe("authStore — setRefreshing", () => {
  it("sets refreshing to true", () => {
    useAuthStore.getState().setRefreshing(true);
    expect(useAuthStore.getState().isRefreshing).toBe(true);
  });

  it("sets refreshing back to false", () => {
    useAuthStore.setState({ isRefreshing: true });
    useAuthStore.getState().setRefreshing(false);
    expect(useAuthStore.getState().isRefreshing).toBe(false);
  });
});

describe("authStore — setInitialized", () => {
  it("marks store as initialized", () => {
    useAuthStore.getState().setInitialized();
    expect(useAuthStore.getState().isInitialized).toBe(true);
  });
});

describe("authStore — selectors", () => {
  it("selectAccessToken returns token", () => {
    useAuthStore.getState().setAuth("my-token", mockUser);
    expect(selectAccessToken(useAuthStore.getState())).toBe("my-token");
  });

  it("selectUser returns user profile", () => {
    useAuthStore.getState().setAuth("my-token", mockUser);
    expect(selectUser(useAuthStore.getState())).toEqual(mockUser);
  });

  it("selectIsAuthenticated is false when no token", () => {
    expect(selectIsAuthenticated(useAuthStore.getState())).toBe(false);
  });

  it("selectIsAuthenticated is true when token present", () => {
    useAuthStore.getState().setAuth("my-token", mockUser);
    expect(selectIsAuthenticated(useAuthStore.getState())).toBe(true);
  });

  it("selectIsRefreshing reflects refreshing state", () => {
    useAuthStore.getState().setRefreshing(true);
    expect(selectIsRefreshing(useAuthStore.getState())).toBe(true);
  });

  it("selectIsInitialized reflects initialized state", () => {
    useAuthStore.getState().setInitialized();
    expect(selectIsInitialized(useAuthStore.getState())).toBe(true);
  });
});
