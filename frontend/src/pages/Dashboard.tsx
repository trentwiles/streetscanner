import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AppShell, Group, Title, Text, Tabs, SimpleGrid, Card, Badge,
  Table, Pagination, Select, ActionIcon, Loader, Center, Stack,
  Tooltip, Button, Modal,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { IconTrash, IconEye, IconLogout, IconEraser } from '@tabler/icons-react'
import { apiFetch } from '../api/client'
import { notifications } from '@mantine/notifications'

// ── Types ──────────────────────────────────────────────────────────────────

interface Stats {
  jobs_total: number
  emails_pending: number
  emails_sent: number
  errors_24h: number
}

interface Job {
  request_id: string
  email: string
  origin_city: string
  dest_city: string
  days: string[]
  submit_time: string
  submit_ip: string | null
  submit_user_agent: string | null
}

interface Email {
  id: number
  request_id: string
  email: string
  subject: string
  created_at: string
  sent_at: string | null
}

interface LogEntry {
  id: number
  created_at: string
  level: string
  company: string | null
  request_id: string | null
  message: string
}

// ── Dashboard ─────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()

  const { data: me, isError: notAuthed } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<{ login: string }>('/auth/me'),
    retry: false,
  })

  useEffect(() => {
    if (notAuthed) navigate('/auth/login')
  }, [notAuthed, navigate])

  const logoutMutation = useMutation({
    mutationFn: () => apiFetch('/auth/logout', { method: 'POST' }),
    onSuccess: () => navigate('/auth/login'),
  })

  if (!me) return <Center h="100vh"><Loader /></Center>

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={4}>StreetScanner Admin</Title>
          <Group gap="xs">
            <Text size="sm" c="dimmed">@{me.login}</Text>
            <Tooltip label="Sign out">
              <ActionIcon variant="subtle" onClick={() => logoutMutation.mutate()}>
                <IconLogout size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <StatsRow />

        <Tabs defaultValue="jobs" mt="md">
          <Tabs.List>
            <Tabs.Tab value="jobs">Jobs</Tabs.Tab>
            <Tabs.Tab value="email-queue">Email Queue</Tabs.Tab>
            <Tabs.Tab value="logs">Logs</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="jobs" pt="md">
            <JobsTab />
          </Tabs.Panel>
          <Tabs.Panel value="email-queue" pt="md">
            <EmailQueueTab />
          </Tabs.Panel>
          <Tabs.Panel value="logs" pt="md">
            <LogsTab />
          </Tabs.Panel>
        </Tabs>
      </AppShell.Main>
    </AppShell>
  )
}

// ── Stats row ─────────────────────────────────────────────────────────────

function StatsRow() {
  const { data } = useQuery({
    queryKey: ['stats'],
    queryFn: () => apiFetch<Stats>('/api/stats'),
    refetchInterval: 10_000,
  })

  const cards = [
    { label: 'Jobs', value: data?.jobs_total ?? '—' },
    { label: 'Emails pending', value: data?.emails_pending ?? '—' },
    { label: 'Emails sent', value: data?.emails_sent ?? '—' },
    { label: 'Errors (24h)', value: data?.errors_24h ?? '—', color: (data?.errors_24h ?? 0) > 0 ? 'red' : undefined },
  ]

  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }}>
      {cards.map(c => (
        <Card key={c.label} withBorder>
          <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{c.label}</Text>
          <Text size="xl" fw={700} c={c.color}>{c.value}</Text>
        </Card>
      ))}
    </SimpleGrid>
  )
}

// ── Jobs tab ──────────────────────────────────────────────────────────────

function JobsTab() {
  const [page, setPage] = useState(1)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['jobs', page],
    queryFn: () => apiFetch<{ jobs: Job[]; total: number }>(`/api/jobs?page=${page}&limit=20`),
    refetchInterval: 10_000,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/jobs/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
      notifications.show({ message: 'Job deleted', color: 'green' })
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: 'red' }),
  })

  if (isLoading) return <Center py="xl"><Loader /></Center>

  const jobs = data?.jobs ?? []
  const totalPages = Math.ceil((data?.total ?? 0) / 20)

  return (
    <Stack>
      <Table highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Email</Table.Th>
            <Table.Th>Route</Table.Th>
            <Table.Th>Days</Table.Th>
            <Table.Th>IP</Table.Th>
            <Table.Th>Submitted</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {jobs.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={6}><Text c="dimmed" ta="center">No jobs</Text></Table.Td>
            </Table.Tr>
          ) : jobs.map(j => (
            <Table.Tr key={j.request_id}>
              <Table.Td>{j.email}</Table.Td>
              <Table.Td>{j.origin_city} → {j.dest_city}</Table.Td>
              <Table.Td>{j.days.join(', ')}</Table.Td>
              <Table.Td>
                {j.submit_ip ? (
                  <Tooltip label={j.submit_user_agent ?? 'Unknown UA'} multiline maw={320} withArrow>
                    <Text
                      size="sm"
                      component="a"
                      href={`https://www.abuseipdb.com/check/${j.submit_ip}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontFamily: 'monospace' }}
                    >
                      {j.submit_ip}
                    </Text>
                  </Tooltip>
                ) : '—'}
              </Table.Td>
              <Table.Td>{j.submit_time ? new Date(j.submit_time).toLocaleString() : '—'}</Table.Td>
              <Table.Td>
                <ActionIcon
                  color="red"
                  variant="subtle"
                  onClick={() => deleteMutation.mutate(j.request_id)}
                  loading={deleteMutation.isPending}
                >
                  <IconTrash size={16} />
                </ActionIcon>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {totalPages > 1 && <Pagination total={totalPages} value={page} onChange={setPage} />}
    </Stack>
  )
}

// ── Email Queue tab ───────────────────────────────────────────────────────

function EmailQueueTab() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string | null>('all')
  const [confirmEmail, setConfirmEmail] = useState<Email | null>(null)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['email-queue', page, status],
    queryFn: () => apiFetch<{ emails: Email[]; total: number }>(`/api/email-queue?page=${page}&limit=20&status=${status ?? 'all'}`),
    refetchInterval: 10_000,
  })

  const deleteMutation = useMutation({
    mutationFn: ({ id, deleteJob }: { id: number; deleteJob: boolean }) =>
      apiFetch(`/api/email-queue/${id}?delete_job=${deleteJob ? '1' : '0'}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['email-queue'] })
      qc.invalidateQueries({ queryKey: ['jobs'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
      notifications.show({ message: 'Email deleted', color: 'green' })
      setConfirmEmail(null)
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: 'red' }),
  })

  if (isLoading) return <Center py="xl"><Loader /></Center>

  const emails = data?.emails ?? []
  const totalPages = Math.ceil((data?.total ?? 0) / 20)

  return (
    <Stack>
      <Group justify="flex-end">
        <Select
          size="xs"
          data={[
            { value: 'all', label: 'All' },
            { value: 'pending', label: 'Pending' },
            { value: 'sent', label: 'Sent' },
          ]}
          value={status}
          onChange={v => { setStatus(v); setPage(1) }}
          w={120}
        />
      </Group>

      <Table highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>To</Table.Th>
            <Table.Th>Subject</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Created</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {emails.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={5}><Text c="dimmed" ta="center">No emails</Text></Table.Td>
            </Table.Tr>
          ) : emails.map(e => (
            <Table.Tr key={e.id}>
              <Table.Td>{e.email}</Table.Td>
              <Table.Td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.subject}</Table.Td>
              <Table.Td>
                <Badge color={e.sent_at ? 'green' : 'yellow'}>
                  {e.sent_at ? 'sent' : 'pending'}
                </Badge>
              </Table.Td>
              <Table.Td>{new Date(e.created_at).toLocaleString()}</Table.Td>
              <Table.Td>
                <Group gap={4} justify="flex-end">
                  <ActionIcon variant="subtle" onClick={() => navigate(`/admin/email-queue/${e.id}/preview`)}>
                    <IconEye size={16} />
                  </ActionIcon>
                  <ActionIcon color="red" variant="subtle" onClick={() => setConfirmEmail(e)}>
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {totalPages > 1 && <Pagination total={totalPages} value={page} onChange={setPage} />}

      <Modal
        opened={!!confirmEmail}
        onClose={() => setConfirmEmail(null)}
        title="Delete email"
        size="sm"
      >
        <Text size="sm" mb="md">
          Delete this email to <strong>{confirmEmail?.email}</strong>? Also delete the associated job request?
        </Text>
        <Group justify="flex-end" gap="sm">
          <Button variant="default" onClick={() => setConfirmEmail(null)}>Cancel</Button>
          <Button
            color="orange"
            loading={deleteMutation.isPending}
            onClick={() => confirmEmail && deleteMutation.mutate({ id: confirmEmail.id, deleteJob: false })}
          >
            Delete email only
          </Button>
          <Button
            color="red"
            loading={deleteMutation.isPending}
            onClick={() => confirmEmail && deleteMutation.mutate({ id: confirmEmail.id, deleteJob: true })}
          >
            Delete email + job
          </Button>
        </Group>
      </Modal>
    </Stack>
  )
}

// ── Logs tab ──────────────────────────────────────────────────────────────

const LEVEL_COLORS: Record<string, string> = {
  error: 'red',
  warning: 'yellow',
  info: 'blue',
}

function LogsTab() {
  const [page, setPage] = useState(1)
  const [level, setLevel] = useState<string | null>('all')
  const [confirmClearAll, setConfirmClearAll] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['logs', page, level],
    queryFn: () => apiFetch<{ logs: LogEntry[]; total: number }>(`/api/logs?page=${page}&limit=50&level=${level ?? 'all'}`),
    refetchInterval: 30_000,
  })

  const deleteOneMutation = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/logs/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['logs'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: 'red' }),
  })

  const clearAllMutation = useMutation({
    mutationFn: () => apiFetch('/api/logs', { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['logs'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
      notifications.show({ message: 'All logs cleared', color: 'green' })
      setConfirmClearAll(false)
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: 'red' }),
  })

  if (isLoading) return <Center py="xl"><Loader /></Center>

  const logs = data?.logs ?? []
  const totalPages = Math.ceil((data?.total ?? 0) / 50)

  return (
    <Stack>
      <Group justify="space-between">
        <Select
          size="xs"
          data={[
            { value: 'all', label: 'All levels' },
            { value: 'error', label: 'Error' },
            { value: 'warning', label: 'Warning' },
            { value: 'info', label: 'Info' },
          ]}
          value={level}
          onChange={v => { setLevel(v); setPage(1) }}
          w={140}
        />
        <Button
          size="xs"
          color="red"
          variant="subtle"
          leftSection={<IconEraser size={14} />}
          onClick={() => setConfirmClearAll(true)}
          disabled={logs.length === 0}
        >
          Clear all logs
        </Button>
      </Group>

      <Table highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Time</Table.Th>
            <Table.Th>Level</Table.Th>
            <Table.Th>Company</Table.Th>
            <Table.Th>Message</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {logs.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={5}><Text c="dimmed" ta="center">No logs</Text></Table.Td>
            </Table.Tr>
          ) : logs.map(l => (
            <Table.Tr key={l.id}>
              <Table.Td style={{ whiteSpace: 'nowrap' }}>{new Date(l.created_at).toLocaleString()}</Table.Td>
              <Table.Td><Badge color={LEVEL_COLORS[l.level] ?? 'gray'}>{l.level}</Badge></Table.Td>
              <Table.Td>{l.company ?? '—'}</Table.Td>
              <Table.Td style={{ fontFamily: 'monospace', fontSize: 13 }}>{l.message}</Table.Td>
              <Table.Td>
                <ActionIcon
                  color="red"
                  variant="subtle"
                  onClick={() => deleteOneMutation.mutate(l.id)}
                  loading={deleteOneMutation.isPending}
                >
                  <IconTrash size={16} />
                </ActionIcon>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {totalPages > 1 && <Pagination total={totalPages} value={page} onChange={setPage} />}

      <Modal
        opened={confirmClearAll}
        onClose={() => setConfirmClearAll(false)}
        title="Clear all logs"
        size="sm"
      >
        <Text size="sm" mb="md">This will permanently delete all log entries. Are you sure?</Text>
        <Group justify="flex-end" gap="sm">
          <Button variant="default" onClick={() => setConfirmClearAll(false)}>Cancel</Button>
          <Button color="red" loading={clearAllMutation.isPending} onClick={() => clearAllMutation.mutate()}>
            Clear all
          </Button>
        </Group>
      </Modal>
    </Stack>
  )
}
