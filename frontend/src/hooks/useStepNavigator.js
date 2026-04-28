import { useCallback, useEffect, useState } from 'react'

export default function useStepNavigator(totalSteps, initialIndex = 0) {
  const clamp = useCallback(
    (value) => {
      if (totalSteps <= 0) return 0
      return Math.max(0, Math.min(totalSteps - 1, value))
    },
    [totalSteps],
  )

  const [activeIndex, setActiveIndex] = useState(() => clamp(initialIndex))

  useEffect(() => {
    setActiveIndex((current) => clamp(current))
  }, [clamp])

  const goToStep = useCallback(
    (index) => {
      setActiveIndex(clamp(index))
    },
    [clamp],
  )

  const next = useCallback(() => {
    setActiveIndex((current) => clamp(current + 1))
  }, [clamp])

  const prev = useCallback(() => {
    setActiveIndex((current) => clamp(current - 1))
  }, [clamp])

  const reset = useCallback(() => {
    setActiveIndex(clamp(initialIndex))
  }, [clamp, initialIndex])

  const isFirst = activeIndex <= 0
  const isLast = totalSteps > 0 ? activeIndex >= totalSteps - 1 : true

  return {
    activeIndex,
    goToStep,
    next,
    prev,
    reset,
    isFirst,
    isLast,
  }
}
