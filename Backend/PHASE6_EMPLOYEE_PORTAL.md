# Phase 6: Employee/Stylist Portal Implementation

## Overview

Phase 6 implements a shop-scoped employee portal with PIN-based authentication, allowing stylists to manage their schedules, acknowledge bookings, update appointment statuses, and request time off - all within their specific shop context.

## Backend Implementation

### New Endpoints (Shop-Scoped: `/s/{slug}/employee/*`)

All employee endpoints are now shop-scoped to support multi-tenancy:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/s/{slug}/employee/stylists-for-login` | Get list of stylists with PINs for login dropdown |
| POST | `/s/{slug}/employee/login` | Authenticate employee with PIN |
| GET | `/s/{slug}/employee/schedule` | Get employee's schedule for a given date |
| POST | `/s/{slug}/employee/bookings/{id}/acknowledge` | Acknowledge a booking |
| POST | `/s/{slug}/employee/bookings/{id}/status` | Update booking status |
| POST | `/s/{slug}/employee/bookings/{id}/notes` | Update booking notes |
| POST | `/s/{slug}/employee/time-off` | Submit time-off request |
| GET | `/s/{slug}/employee/time-off` | Get employee's time-off requests |
| GET | `/s/{slug}/employee/customer/{booking_id}/preferences` | Get customer preferences for a booking |

### Shop Registry Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/registry/shops` | List all available shops for selection |

### Authentication Flow

1. **Session Management**: Sessions are stored in-memory with 12-hour TTL
2. **Token Storage**: Each session stores `{stylist_id, shop_id, expires_at}`
3. **Shop Validation**: Requests are validated against shop context
4. **Token Format**: UUID-based Bearer tokens

### Key Models

```python
# Login Request/Response
class EmployeeLoginRequest(BaseModel):
    stylist_id: int
    pin: str

class EmployeeLoginResponse(BaseModel):
    token: str
    stylist_id: int
    stylist_name: str
    shop_id: int
    shop_name: str
    expires_in: int

# Schedule Response
class EmployeeScheduleBooking(BaseModel):
    id: str
    service_name: str
    customer_name: Optional[str]
    customer_phone: Optional[str]
    customer_email: Optional[str]
    start_time: str
    end_time: str
    appointment_status: str
    acknowledged: bool
    internal_notes: Optional[str]
    customer_preferences: Optional[CustomerPreferences]

# Booking Status Options
- SCHEDULED
- IN_PROGRESS
- RUNNING_LATE
- COMPLETED
- NO_SHOW
```

### Customer Preferences

The employee can view customer preferences for each booking:
- Whether customer prefers this stylist
- Total visits to the shop
- Visits with this specific stylist
- Style preferences (text and image)

## Frontend Implementation

### Shop Selection Page (`/employee`)

- Lists all available shops from `/registry/shops`
- Search/filter functionality
- "Recent shop" quick access via localStorage
- Manual slug entry for direct navigation

### Shop-Scoped Employee Dashboard (`/employee/[slug]`)

Features:
1. **PIN Login**: Select name from dropdown, enter PIN
2. **Date Navigation**: Browse schedule by date
3. **Appointment Cards**:
   - Customer info (name, phone, email)
   - Service details
   - Status badge with color coding
   - Acknowledgement status
   - Customer preferences indicator
4. **Booking Actions**:
   - Acknowledge button
   - Start/Complete/Running Late status transitions
   - No-Show marking
   - Internal notes editing
5. **Customer Preferences Modal**:
   - Visit history
   - Style preferences (text and image)
6. **Time-Off Management**:
   - Request submission form
   - Status tracking (PENDING/APPROVED/REJECTED)

### State Management

Session data is stored in localStorage with shop-specific keys:
- `employee_token_{slug}`
- `employee_stylist_id_{slug}`
- `employee_stylist_name_{slug}`
- `employee_shop_name_{slug}`
- `employee_recent_shop` (for quick access)

## File Changes

### Backend
- `Backend/app/routes_scoped.py` - Added ~600 lines of employee routes
- `Backend/app/registry.py` - Added `/registry/shops` endpoint

### Frontend
- `frontend/src/app/employee/page.tsx` - Replaced with shop selection page
- `frontend/src/app/employee/[slug]/page.tsx` - New shop-scoped employee dashboard

## Testing

### Manual Testing

1. **Shop Selection**:
   ```
   Navigate to /employee
   Should see list of shops
   Select a shop to navigate to /employee/{slug}
   ```

2. **Login**:
   ```
   Select stylist from dropdown
   Enter PIN
   Should receive token and see dashboard
   ```

3. **Schedule**:
   ```
   View today's appointments
   Navigate dates with arrows
   See customer preferences indicators
   ```

4. **Booking Actions**:
   ```
   Acknowledge booking
   Update status (Start → Running Late → Complete)
   Add/edit notes
   View customer preferences
   ```

5. **Time Off**:
   ```
   Submit time-off request
   View pending/approved/rejected requests
   ```

### API Testing with curl

```bash
# List shops
curl http://localhost:8000/registry/shops

# Get stylists for login
curl http://localhost:8000/s/bishops-tempe/employee/stylists-for-login

# Login
curl -X POST http://localhost:8000/s/bishops-tempe/employee/login \
  -H "Content-Type: application/json" \
  -d '{"stylist_id": 1, "pin": "1234"}'

# Get schedule (with token)
curl http://localhost:8000/s/bishops-tempe/employee/schedule?date_str=2025-01-15 \
  -H "Authorization: Bearer {token}"
```

## Security Notes

1. PIN authentication is for convenience, not high security
2. Sessions expire after 12 hours
3. Shop context is validated on every request
4. Stylists can only access their own bookings
5. Customer phone/email is visible for contact purposes

## Legacy Compatibility

The original `/employee/*` endpoints in `main.py` remain for backward compatibility. They operate on `LEGACY_DEFAULT_SHOP_ID`. New deployments should use the shop-scoped endpoints.

## Next Steps

- [ ] Add audit logging for booking status changes
- [ ] Implement push notifications for new bookings
- [ ] Add real-time updates via WebSocket
- [ ] Consider rate limiting on login endpoint
- [ ] Add password change functionality
