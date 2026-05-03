import { useState } from 'react'
import {
  Container, Title, Paper, TextInput, Select, CheckboxGroup, Checkbox,
  Button, Stack, Text, Alert, Group,
} from '@mantine/core'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { IconCheck } from '@tabler/icons-react'

interface City { id: string; name: string }

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function SubmitJob() {
  const [email, setEmail] = useState('')
  const [origin, setOrigin] = useState<string | null>(null)
  const [dest, setDest] = useState<string | null>(null)
  const [days, setDays] = useState<string[]>([])
  const [submitted, setSubmitted] = useState<string | null>(null)

  const { data: citiesData } = useQuery({
    queryKey: ['cities'],
    queryFn: () => apiFetch<{ cities: City[] }>('/api/cities'),
  })

  const cities = citiesData?.cities ?? []
  const cityOptions = cities.map(c => ({ value: c.id, label: c.name }))

  const mutation = useMutation({
    mutationFn: () =>
      apiFetch<{ pending: boolean }>('/api/jobs', {
        method: 'POST',
        body: JSON.stringify({ email, origin_city: origin, dest_city: dest, days }),
      }),
    onSuccess: () => setSubmitted(email),
  })

  if (submitted) {
    return (
      <Container size="sm" pt={80}>
        <Alert icon={<IconCheck />} color="green" title="Check your email!" mb="md">
          <Text>We sent a confirmation link to <strong>{submitted}</strong>. Click the link to activate your price alerts.</Text>
        </Alert>
        <Button variant="default" onClick={() => setSubmitted(null)}>
          Submit another request
        </Button>
      </Container>
    )
  }

  return (
    <Container size="sm" pt={80}>
      <Title order={1} mb="xs">StreetScanner</Title>
      <Text c="dimmed" mb="xl">Find the cheapest bus tickets on your preferred travel days.</Text>

      <Paper withBorder p="xl" radius="md">
        <Stack gap="md">
          <TextInput
            label="Email address"
            placeholder="you@example.com"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
          />

          <Select
            label="Origin city"
            placeholder="Select city"
            data={cityOptions}
            value={origin}
            onChange={setOrigin}
            required
          />

          <Select
            label="Destination city"
            placeholder="Select city"
            data={cityOptions}
            value={dest}
            onChange={setDest}
            required
          />

          <CheckboxGroup
            label="Travel days"
            description="Which days of the week should we check?"
            value={days}
            onChange={setDays}
          >
            <Group mt="xs" gap="sm">
              {DAYS.map(d => (
                <Checkbox key={d} value={d} label={d} />
              ))}
            </Group>
          </CheckboxGroup>

          {mutation.isError && (
            <Text c="red" size="sm">{(mutation.error as Error).message}</Text>
          )}

          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!email || !origin || !dest || days.length === 0}
          >
            Submit
          </Button>
        </Stack>
      </Paper>

      <Text size="xs" c="dimmed" mt="md" ta="center">
        <a href="/auth/login">Admin login</a>
      </Text>
    </Container>
  )
}
