import { Container, Title, Paper, Button, Text, Alert, Stack } from '@mantine/core'
import { IconBrandGithub, IconAlertCircle } from '@tabler/icons-react'
import { useSearchParams } from 'react-router-dom'

export default function Login() {
  const [params] = useSearchParams()
  const error = params.get('error')

  return (
    <Container size="xs" pt={120}>
      <Title order={2} ta="center" mb="xl">Admin Login</Title>

      <Paper withBorder p="xl" radius="md">
        <Stack gap="md">
          {error === 'unauthorized' && (
            <Alert icon={<IconAlertCircle />} color="red" title="Access denied">
              Your GitHub account is not authorized to access this admin panel.
            </Alert>
          )}

          <Text c="dimmed" size="sm" ta="center">
            Sign in with your GitHub account to access the admin dashboard.
          </Text>

          <Button
            component="a"
            href="/auth/login"
            leftSection={<IconBrandGithub size={18} />}
            variant="filled"
            fullWidth
          >
            Sign in with GitHub
          </Button>
        </Stack>
      </Paper>
    </Container>
  )
}
