// app.ts
import { miniLogin } from './utils/api'

interface UserSession {
  registered: boolean
  accessToken?: string
  tenantName?: string
  contactName?: string
  accountId?: string
  tenantId?: string
  openid?: string  // only set when not registered
  unionid?: string // only set when not registered and available
}

App<IAppOption>({
  globalData: {
    session: null as UserSession | null,
  },

  onLaunch() {
    // Intentionally empty — auth flow is driven by the index page
  },
})