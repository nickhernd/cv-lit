// Tests de AutoMode.vue — primera ronda de tests automáticos de frontend del
// proyecto (2026-08-11), cubriendo el formulario, la llamada a /start y el
// filtrado del log de actividad. No mockea el componente, solo `fetch` (única
// frontera real con el exterior) — todo lo demás (reactividad, plantilla,
// validación) corre con Vue real vía @vue/test-utils.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import AutoMode from '../AutoMode.vue'

const CAMERAS = [
  { idx: 1, id: 'C1', name: 'CAM 1 (Norte)', calibrated: true, rmse_m: 0.35 },
  { idx: 2, id: 'C2', name: 'CAM 2 (Norte Centro)', calibrated: false, rmse_m: null },
]

function mockFetchRouter(routes) {
  return vi.fn((url) => {
    for (const [pattern, handler] of routes) {
      if (typeof pattern === 'string' ? url.includes(pattern) : pattern.test(url)) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(handler) })
      }
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
  })
}

let wrapper

afterEach(() => {
  wrapper?.unmount()
  vi.restoreAllMocks()
})

describe('AutoMode.vue — formulario inicial', () => {
  beforeEach(async () => {
    global.fetch = mockFetchRouter([
      ['/api/cameras', CAMERAS],
      ['/api/logs', []],
    ])
    wrapper = mount(AutoMode)
    await flushPromises()
  })

  it('carga las cámaras y preselecciona la primera calibrada', async () => {
    const options = wrapper.findAll('option')
    expect(options.length).toBe(2)
    expect(wrapper.text()).toContain('CAM 1 (Norte)')
  })

  it('deshabilita el botón de inicio si la cámara seleccionada no está calibrada', async () => {
    const select = wrapper.find('select')
    await select.setValue('2')
    await flushPromises()
    const startBtn = wrapper.findAll('button').find(b => b.text().includes('Iniciar procesamiento automático'))
    expect(startBtn.attributes('disabled')).toBeDefined()
  })

  it('habilita el botón de inicio con la cámara calibrada (preseleccionada por defecto)', () => {
    const startBtn = wrapper.findAll('button').find(b => b.text().includes('Iniciar procesamiento automático'))
    expect(startBtn.attributes('disabled')).toBeUndefined()
  })

  it('muestra el panel de estado por cámara con datos reales', () => {
    expect(wrapper.text()).toContain('Estado por cámara')
    expect(wrapper.text()).toContain('CAM 2 (Norte Centro)')
    expect(wrapper.text()).toContain('Sin calibrar')
  })
})

describe('AutoMode.vue — inicio de job', () => {
  beforeEach(async () => {
    global.fetch = mockFetchRouter([
      ['/api/cameras', CAMERAS],
      ['/api/logs', []],
    ])
    wrapper = mount(AutoMode)
    await flushPromises()
  })

  it('envía cam_id, from_date y to_date correctos al pulsar Iniciar', async () => {
    const postCalls = []
    global.fetch = vi.fn((url, opts) => {
      if (url.includes('/api/automode/start')) {
        postCalls.push(JSON.parse(opts.body))
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ job_id: 'abc123' }) })
      }
      if (url.includes('/api/automode/abc123/status')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'pending', step: '', progress: { current: 0, total: 0 } }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('Iniciar procesamiento automático'))
    await startBtn.trigger('click')
    await flushPromises()

    expect(postCalls).toHaveLength(1)
    expect(postCalls[0].cam_id).toBe(1)
    expect(postCalls[0].from_date).toBeTruthy()
    expect(postCalls[0].to_date).toBeTruthy()
  })
})

describe('AutoMode.vue — log de actividad filtrado', () => {
  it('solo muestra mensajes con el prefijo "Auto Mode"', async () => {
    global.fetch = mockFetchRouter([
      ['/api/cameras', CAMERAS],
      ['/api/logs', [
        { time: '10:00:00', type: 'info', msg: 'Auto Mode Cam 1: descargando 2026-08-01 → 2026-08-08' },
        { time: '10:00:05', type: 'info', msg: 'Homografía Cam 3 calculada' },
        { time: '10:00:10', type: 'success', msg: 'Auto Mode Cam 1: completado' },
      ]],
    ])
    wrapper = mount(AutoMode)
    await flushPromises()

    const logText = wrapper.text()
    expect(logText).toContain('descargando 2026-08-01')
    expect(logText).toContain('completado')
    expect(logText).not.toContain('Homografía Cam 3 calculada')
  })
})

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}
