// 0. 로그인 (정보 구조도 3장, API 명세 3장).
//
// 흐름: 이메일·비밀번호 → POST /auth/login → 서버가 세션 쿠키를 심는다
//       → landingPath()가 GET /domains로 갈 곳을 정한다(등록 또는 대시보드)
// 오류: 401 INVALID_CREDENTIALS → "이메일 또는 비밀번호가 맞지 않습니다."
//       429 TOO_MANY_ATTEMPTS  → "5분 뒤 다시 시도해 주세요."
// 세션이 끝나 넘어왔으면(state.expired) 위에 "다시 로그인해 주세요."를 보여 준다.

import { Text, VStack } from '@seed-design/react'
import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ActionButton } from 'seed-design/ui/action-button'
import { Callout } from 'seed-design/ui/callout'
import { TextField, TextFieldInput } from 'seed-design/ui/text-field'
import { ApiError, USE_MOCK } from '../api/client'
import { api } from '../api/endpoints'
import { Surface } from '../components/Surface'
import { AuthLayout } from '../layout/AuthLayout'
import { landingPath } from '../lib/landing'

export function LoginPage() {
  const navigate = useNavigate()
  const expired = (useLocation().state as { expired?: boolean } | null)?.expired
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(undefined)
    try {
      await api.auth.login(email.trim(), password)
      navigate(await landingPath(), { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '로그인하지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout>
      <Surface p="x8">
        <form onSubmit={submit} noValidate>
          <VStack gap="x6">
            <VStack gap="x2">
              <Text as="h1" textStyle="t9Bold" color="fg.neutral">
                로그인
              </Text>
              <Text as="p" textStyle="t4Regular" color="fg.neutralMuted">
                시연용 계정으로 로그인합니다.
              </Text>
            </VStack>

            {expired && <Callout tone="warning" description="다시 로그인해 주세요." />}
            {error && <Callout tone="critical" description={error} />}

            <TextField label="이메일" value={email} onValueChange={({ value }) => setEmail(value)}>
              <TextFieldInput type="email" autoComplete="username" placeholder="admin@jobnest.test" required />
            </TextField>
            <TextField label="비밀번호" value={password} onValueChange={({ value }) => setPassword(value)}>
              <TextFieldInput type="password" autoComplete="current-password" required />
            </TextField>

            <ActionButton type="submit" variant="brandSolid" size="large" loading={busy} disabled={!email || !password}>
              로그인
            </ActionButton>

            {USE_MOCK && (
              <Text textStyle="t3Regular" color="fg.neutralSubtle">
                가짜 응답 모드 계정: admin@jobnest.test / a2d-demo
              </Text>
            )}
          </VStack>
        </form>
      </Surface>
    </AuthLayout>
  )
}
