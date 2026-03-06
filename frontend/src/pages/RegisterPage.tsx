/**
 * RegisterPage -- new user + organization registration form.
 *
 * Fields: email, password, display name, organization name.
 * On success stores the token and redirects to /.
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
import { useRegister } from '@/api/hooks/useAuth'
import { Link2 } from 'lucide-react'

export default function RegisterPage() {
  const navigate = useNavigate()
  const register = useRegister()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [orgName, setOrgName] = useState('')

  const errorMessage =
    register.error instanceof Error ? register.error.message : null

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    register.mutate(
      { email, password, displayName, orgName },
      {
        onSuccess: () => {
          navigate({ to: '/' })
        },
      },
    )
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-12"
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
          <CardTitle className="text-2xl">Create your lab</CardTitle>
          <CardDescription>
            Set up a new LabLink organization
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
                {errorMessage}
              </div>
            )}

            <InputGroup label="Full name" htmlFor="displayName" required>
              <Input
                id="displayName"
                type="text"
                placeholder="Dr. Jane Smith"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                autoComplete="name"
              />
            </InputGroup>

            <InputGroup label="Organization name" htmlFor="orgName" required>
              <Input
                id="orgName"
                type="text"
                placeholder="Acme Research Lab"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                required
                autoComplete="organization"
              />
            </InputGroup>

            <InputGroup label="Email" htmlFor="email" required>
              <Input
                id="email"
                type="email"
                placeholder="you@lab.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </InputGroup>

            <InputGroup label="Password" htmlFor="password" required>
              <Input
                id="password"
                type="password"
                placeholder="At least 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </InputGroup>
          </CardContent>

          <CardFooter className="flex-col gap-4">
            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full"
              loading={register.isPending}
            >
              Create account
            </Button>

            <p
              className="text-sm font-medium text-center"
              style={{ color: '#64748b' }}
            >
              Already have an account?{' '}
              <Link
                to="/login"
                className="font-bold"
                style={{ color: '#3b82f6' }}
              >
                Sign in
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  )
}
