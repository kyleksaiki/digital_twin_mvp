export function buildAssistantContext(loadedRun, summaryData) {
  const runContext = loadedRun
    ? {
        id: loadedRun.id,
        name: loadedRun.name,
        status: loadedRun.status,
        duration: loadedRun.duration,
      }
    : null

  return {
    mode: runContext ? 'run-specific' : 'general',
    run: runContext,
    summary: summaryData?.content || null,
    availableTopics: ['run-metrics', 'visualizations', 'system-behavior', 'confidence'],
    generatedAt: new Date().toISOString(),
  }
}
