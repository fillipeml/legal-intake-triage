# Microsoft 365 setup

The production adapters read one mailbox, send from the areas' mailboxes and use Planner, all through Microsoft Graph with app-only authentication. The demo needs none of this.

## The intake account

One service account (`INTAKE_MAILBOX`, e.g. `intake@lawfirm.example`) with a mailbox. It is added as a **member and subscriber** of every area group whose mailbox is an intake address, so that every message to the group lands in its inbox. For an area that uses a separate list as the intake address, create a distribution list whose only member is the intake account (an alias does not work: Exchange rewrites the `To` of internal mail to the primary address, and the routing condition would never see it).

Lawyers who do not want a copy of everything that reaches the group unsubscribe from it; the intake account must stay subscribed, or the automation stops in silence.

## App registration

1. Entra ID → App registrations → New registration (single tenant). Note the tenant id and the client id; create a client secret and note its expiry.
2. API permissions → Microsoft Graph → **Application** permissions:
   - `Mail.Read`, `Mail.ReadWrite` (the sweep, and the card as a reply in the thread) and `Mail.Send` (the reply to the client from the area's mailbox);
   - `Tasks.ReadWrite.All` (buckets, tasks, details, labels);
   - `Group.Read.All` and `User.Read.All` (the lawyers' user ids for assignments).
3. Grant admin consent.
4. Restrict the app's mailbox access with an Exchange Online application access policy to the intake account and the areas' mailboxes:

```powershell
Connect-ExchangeOnline
New-ApplicationAccessPolicy -AppId <client id> -PolicyScopeGroupId sg-intake-automation@lawfirm.example `
    -AccessRight RestrictAccess -Description "legal intake: intake and area mailboxes only"
```

## Planner

Each area's `board.plan` is the id of its plan (the last segment of the plan's URL). Buckets are the clients; the fallback bucket (`OTHERS` by default) receives demands without a client. Labels are the plan's categories: set `label` on each work type to the category key (`category1` ... `category25`) after naming the categories in the plan's settings; `null` applies no label.

## The decision endpoint

In production the Outlook card posts the decision to `POST /api/decisions` of the console with a bearer token. The shipped endpoint checks `CONSOLE_SECRET`; a deployment on the Microsoft Actionable Messages platform registers a provider, exposes an App ID URI on an app registration and validates the Entra token the card carries (signature through the tenant's JWKS, issuer, audience, the Actions app as the caller, the actor's domain), then forwards the decision. The console's form does the same decision for clients that do not render the card, behind the console's session.

## Environment

```
INTAKE_MAILBOX=intake@lawfirm.example
INTERNAL_DOMAIN=lawfirm.example
MS_TENANT_ID=...
MS_CLIENT_ID=...
MS_CLIENT_SECRET=...
ANTHROPIC_API_KEY=...
DEMO_MODE=false
DRY_RUN=true
```

Start with `DRY_RUN=true`: the sweep reads, triages, records and logs what it would send; nothing leaves. Switch it off when the registry looks right for a few days. Schedule `intake sweep` every fifteen minutes on business hours and `intake sync-board` hourly (`scripts/register_scheduled_task.ps1` on Windows, or the container from any scheduler).
