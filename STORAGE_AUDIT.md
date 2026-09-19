# PULS Media and File Storage Audit

Production read-only audit date: 2026-09-19. No bucket, policy, object, schema, or business row was changed.

| Type | Current storage | DB reference | Actual file location | Private/Public | Retention | Used by |
| --- | --- | --- | --- | --- | --- | --- |
| Vehicle photos uploaded by users | Supabase Storage bucket `vehicle-photos` (8 objects at audit time) | `vehicles.photo_url` | `vehicle-photos/<auth_uid>/<vehicle_id>/<timestamp>-<safe-name>.<ext>` | Public bucket; authenticated INSERT/UPDATE/DELETE policies restrict object paths to the caller's UID folder | No automatic TTL found. Replaced/removed photos are deleted by the frontend; moving a vehicle to Trash preserves the photo | My Car vehicle identity card |
| Support images | Supabase Storage bucket `support-attachments` (6 residual objects) | None in the current production public schema; `support_requests` and `attachment_url` are absent | Historical layout: `support-attachments/<user-or-guest>/<YYYY>/<MM>/<DD>/<uuid>-<safe-name>.<ext>` | Public bucket. No current `storage.objects` policy was found for this bucket; historical backend used service-role upload | No automatic TTL or cleanup found | Historical support intake implementation; current backend has no `/api/support` route |
| My Car service-record photos | Browser `localStorage` as inline data URLs under `puls_service_records_v1` | None | The current browser profile/origin storage, embedded in each local service record | Local to the browser profile, not a public URL | Up to 200 local records; retained until record deletion or browser storage clearing | My Car service-history cards |
| User avatar | No active upload/storage integration found | `users.avatar_url` exists | Whatever external URL a row may contain; no owned bucket path is defined in current code | Undetermined per external URL | No application cleanup found | No active frontend/backend consumer found in the audited code |
| Knowledge images | No owned file storage | `sources.url`; optional source-page URL in `sources.metadata`; relations in `knowledge_sources` | Original external website/CDN | External/public according to source | Controlled by the external source; PULS retains only the URL/metadata | Search results, Knowledge Library provenance, chat visual results |
| PDFs and manuals | No owned file storage | `sources.url` + `knowledge_sources` | Original external manual/PDF page | External/public according to source | Controlled by the external source | Knowledge Library and Search evidence |
| Uploaded Knowledge documents/files | Not implemented | None | None | None | None | Admin Upload File remains disabled |
| Videos and external video URLs | No owned file storage | `sources.url` and response links | YouTube/Rutube/Vimeo or other external host | External/public according to source | Controlled by the external source | Search, Knowledge Library, chat sources |
| Generated/external image URLs | No owned file storage | Search link payloads and `sources.url`; vehicle enrichment may persist a remote URL in `vehicles.photo_url` | Original provider/Wikipedia/Wikimedia/CDN URL | External/public according to source | Controlled by the external source | Chat visual results and automatic vehicle-photo enrichment |

## Production Storage facts

- Existing buckets: `vehicle-photos` (public, 8 objects) and `support-attachments` (public, 6 objects).
- No private bucket exists for Knowledge files.
- `vehicle-photos` has authenticated INSERT/UPDATE/DELETE policies constrained to the caller's UID folder.
- No current `storage.objects` policy was found for `support-attachments`.
- No automatic object-retention or scheduled cleanup policy was found.
- Current public media URL columns are only `sources.url`, `users.avatar_url`, and `vehicles.photo_url`.

## Delete boundary

Admin database deletion never deletes Storage objects or canonical `sources` rows. This is deliberate: Storage deletion cannot participate in the same database transaction, and source URLs/files may be shared. The delete preview explicitly reports that boundary. A future file-management design must define ownership, private bucket policy, reference counting, and transactional/retry behavior before file deletion or Knowledge upload is enabled.
