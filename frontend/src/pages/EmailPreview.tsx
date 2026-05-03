import { useParams, useNavigate } from 'react-router-dom'
import { Container, Title, Button, Group, Paper, Loader, Center, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { IconArrowLeft } from '@tabler/icons-react'

export default function EmailPreview() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: html, isLoading, isError } = useQuery({
    queryKey: ['email-preview', id],
    queryFn: async () => {
      const res = await fetch(`/api/email-queue/${id}/preview`, { credentials: 'include' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.text()
    },
  })

  return (
    <Container size="lg" pt="md">
      <Group mb="md">
        <Button
          variant="subtle"
          leftSection={<IconArrowLeft size={16} />}
          onClick={() => navigate('/admin')}
        >
          Back to dashboard
        </Button>
        <Title order={4}>Email #{id} Preview</Title>
      </Group>

      <Paper withBorder style={{ overflow: 'hidden' }}>
        {isLoading && <Center p="xl"><Loader /></Center>}
        {isError && <Text c="red" p="md">Failed to load email preview.</Text>}
        {html && (
          <iframe
            srcDoc={html}
            style={{ width: '100%', height: '80vh', border: 'none' }}
            title="Email preview"
            sandbox="allow-same-origin"
          />
        )}
      </Paper>
    </Container>
  )
}
