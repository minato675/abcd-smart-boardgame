/// <reference types="vite/client" />

/**
 * .env 로 주입되는 값들.
 * ImportMeta 자체는 vite/client 가 이미 선언하므로 여기서는 키만 보강한다.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_ROOM_NUMBER?: string
  readonly VITE_ROOM_LABEL?: string
  readonly VITE_CAFE_NAME?: string
  readonly VITE_MQTT_URL?: string
  readonly VITE_MQTT_USERNAME?: string
  readonly VITE_MQTT_PASSWORD?: string
  readonly VITE_CABINET_CONTROLLER_ID?: string
  readonly VITE_ADMIN_ROOM_NUMBERS?: string
}
