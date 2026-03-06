/**
 * LoginPage -- email + password authentication form.
 *
 * Neuromorphic design:
 *   - Centered card with nm-outset shadow
 *   - nm-inset input fields
 *   - nm-glow-blue submit button
 *   - Error display with suggestion text
 */

import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from '@tanstack/react-router'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Input,
  InputGroup,
  Button,
} from '@/components/ui'
import { useLogin } from '@/api/hooks/useAuth'
import { Link2 } from 'lucide-react'

export default function LoginPage() {
  const navigate = useNavigate()
  const login = useLogin()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const errorMessage =
    login.error instanceof Error ? login.error.message : null
  // Try to extract suggestion from the error message (format: "[CODE] msg -- suggestion")
  const suggestion = errorMessage?.includes(' -- ')
    ? errorMessage.split(' -- ')[1]
    : null

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    login.mutate(
      { email, password },
      {
        onSuccess: () => {
          navigate({ to: '/' })
        },
      },
    )
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ backgroundColor: 'var(--bg, #f5f7fa)' }}
    >
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          {/* Logo */}
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
            style={{
              backgroundColor: '#3b82f6',
              boxShadow:
                '0 0 25px rgba(59,130,246,0.4), 4px 4px 8px rgba(174,185,201,0.4), -4px -4px 8px rgba(255,255,255,0.9)',
            }}
          >
            <Link2 size={24} strokeWidth={2.5} className="text-white" />
          </div>
          <CardTitle className="text-2xl">Welcome back</CardTitle>
          <CardDescription>
            Sign in to your LabLink account
          </CardDescription>
        </CardHeader>

        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-5">
            {/* Error display */}
            {errorMessage && (
              <div
                className="rounded-2xl px-5 py-4 text-sm font-medium"
                style={{
                  backgroundColor: '#f5f7fa',
                  boxShadow:
                    'inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)',
                  color: '#ef4444',
                }}
              >
                <p>{errorMessage}</p>
                {suggestion && (
                  <p className="mt-1 text-xs" style={{ color: '#94a3b8' }}>
                    {suggestion}
                  </p>
                )}
              </div>
            )}

            <InputGroup
              label="Email"
              htmlFor="email"
              required
            >
              <Input
                id="email"
                type="email"
                placeholder="you@lab.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                error={Boolean(login.error)}
              />
            </InputGroup>

            <InputGroup
              label="Password"
              htmlFor="password"
              required
            >
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                error={Boolean(login.error)}
              />
            </InputGroup>
          </CardContent>

          <CardFooter className="flex-col gap-4">
            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full"
              loading={login.isPending}
            >
              Sign in
            </Button>

            <p
              className="text-sm font-medium text-center"
              style={{ color: '#64748b' }}
            >
              Don't have an account?{' '}
              <Link
                to="/register"
                className="font-bold"
                style={{ color: '#3b82f6' }}
              >
                Create one
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  )
}
