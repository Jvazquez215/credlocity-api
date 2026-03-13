"""
E-Signature API for Credlocity Outsourcing Service Agreements
Provides: signing token generation, public signing page, signature embedding
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import hashlib
import io

esign_router = APIRouter(prefix="/api/esign")

db = None

def set_db(database):
    global db
    db = database

from auth import decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _generate_sign_token(agreement_id: str) -> str:
    raw = f"{agreement_id}:{uuid4().hex}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


@esign_router.post("/send/{agreement_id}")
async def send_for_signature(agreement_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Admin sends an agreement for e-signature. Creates a signing token and updates agreement."""
    agreement = await db.outsource_agreements.find_one({"id": agreement_id}, {"_id": 0})
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    signer_name = data.get("signer_name", "")
    signer_email = data.get("signer_email", "")

    if not signer_name or not signer_email:
        raise HTTPException(status_code=400, detail="Signer name and email are required")

    sign_token = _generate_sign_token(agreement_id)
    now = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    sign_request = {
        "id": str(uuid4()),
        "agreement_id": agreement_id,
        "sign_token": sign_token,
        "signer_name": signer_name,
        "signer_email": signer_email,
        "status": "pending",
        "sent_by": user.get("id"),
        "sent_by_name": user.get("full_name", user.get("email", "")),
        "sent_at": now,
        "expires_at": expires_at,
        "signed_at": None,
        "signature_data": None,
        "signer_ip": None,
    }

    await db.esign_requests.insert_one(sign_request)
    sign_request.pop("_id", None)

    # Update agreement status to 'sent_for_signing'
    await db.outsource_agreements.update_one(
        {"id": agreement_id},
        {"$set": {"status": "sent_for_signing", "esign_request_id": sign_request["id"]}}
    )

    return {
        "message": "Agreement sent for e-signature",
        "sign_request_id": sign_request["id"],
        "sign_token": sign_token,
        "signer_email": signer_email,
        "expires_at": expires_at
    }


@esign_router.get("/requests/{agreement_id}")
async def get_sign_requests(agreement_id: str, user: dict = Depends(get_current_user)):
    """Get all e-sign requests for an agreement."""
    requests = await db.esign_requests.find(
        {"agreement_id": agreement_id}, {"_id": 0}
    ).sort("sent_at", -1).to_list(50)
    return requests


# ==================== PUBLIC SIGNING ENDPOINTS (NO AUTH) ====================

@esign_router.get("/public/verify/{sign_token}")
async def verify_sign_token(sign_token: str):
    """Public: Verify a signing token and return agreement info for display."""
    sign_request = await db.esign_requests.find_one({"sign_token": sign_token}, {"_id": 0})
    if not sign_request:
        raise HTTPException(status_code=404, detail="Invalid or expired signing link")

    if sign_request.get("status") == "signed":
        return {"status": "already_signed", "signed_at": sign_request.get("signed_at"), "signer_name": sign_request.get("signer_name")}

    # Check expiry
    expires_at = sign_request.get("expires_at", "")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if datetime.now(timezone.utc) > expiry:
                return {"status": "expired"}
        except (ValueError, TypeError):
            pass

    # Get agreement details
    agreement = await db.outsource_agreements.find_one(
        {"id": sign_request["agreement_id"]}, {"_id": 0}
    )
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    # Get partner info
    partner = await db.outsource_partners.find_one(
        {"id": agreement.get("partner_id")}, {"_id": 0, "company_name": 1, "contact_name": 1}
    )

    return {
        "status": "pending",
        "signer_name": sign_request.get("signer_name"),
        "signer_email": sign_request.get("signer_email"),
        "agreement": {
            "id": agreement.get("id"),
            "package_name": agreement.get("package_name"),
            "rate_per_account": agreement.get("rate_per_account"),
            "min_accounts": agreement.get("min_accounts"),
            "max_accounts": agreement.get("max_accounts"),
            "provider_name": agreement.get("provider_name", "Credlocity LLC"),
            "created_at": agreement.get("created_at"),
        },
        "partner": {
            "company_name": partner.get("company_name", "") if partner else "",
        },
        "expires_at": expires_at
    }


@esign_router.post("/public/sign/{sign_token}")
async def sign_agreement(sign_token: str, data: dict, request: Request):
    """Public: Submit signature for an agreement."""
    sign_request = await db.esign_requests.find_one({"sign_token": sign_token}, {"_id": 0})
    if not sign_request:
        raise HTTPException(status_code=404, detail="Invalid signing link")

    if sign_request.get("status") == "signed":
        raise HTTPException(status_code=400, detail="This agreement has already been signed")

    signature_data = data.get("signature_data")
    if not signature_data:
        raise HTTPException(status_code=400, detail="Signature is required")

    # Get signer IP
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    now = datetime.now(timezone.utc).isoformat()

    # Update sign request
    await db.esign_requests.update_one(
        {"sign_token": sign_token},
        {"$set": {
            "status": "signed",
            "signed_at": now,
            "signature_data": signature_data,
            "signer_ip": client_ip,
        }}
    )

    # Update agreement status to 'signed'
    await db.outsource_agreements.update_one(
        {"id": sign_request["agreement_id"]},
        {"$set": {"status": "signed", "signed_at": now, "signed_by": sign_request.get("signer_name")}}
    )

    return {
        "message": "Agreement signed successfully",
        "signed_at": now,
        "signer_name": sign_request.get("signer_name")
    }


@esign_router.get("/public/download/{sign_token}")
async def download_signed_agreement(sign_token: str):
    """Public: Download the agreement PDF (for signed agreements)."""
    sign_request = await db.esign_requests.find_one({"sign_token": sign_token}, {"_id": 0})
    if not sign_request:
        raise HTTPException(status_code=404, detail="Invalid signing link")

    agreement = await db.outsource_agreements.find_one(
        {"id": sign_request["agreement_id"]}, {"_id": 0}
    )
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    # Generate PDF with signature
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        import base64

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=12)
        body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=14)
        bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=10, leading=14, fontName='Helvetica-Bold')

        story.append(Paragraph("CREDIT REPAIR OUTSOURCING SERVICE AGREEMENT", title_style))
        story.append(Spacer(1, 0.2*inch))

        partner = await db.outsource_partners.find_one({"id": agreement.get("partner_id")}, {"_id": 0})
        partner_name = partner.get("company_name", "Partner") if partner else "Partner"

        story.append(Paragraph(f"<b>Provider:</b> {agreement.get('provider_name', 'Credlocity LLC')}", body_style))
        story.append(Paragraph(f"<b>Client:</b> {partner_name}", body_style))
        story.append(Paragraph(f"<b>Package:</b> {agreement.get('package_name', 'N/A')}", body_style))
        story.append(Paragraph(f"<b>Rate:</b> ${agreement.get('rate_per_account', 0):.2f} per account", body_style))
        story.append(Paragraph(f"<b>Account Range:</b> {agreement.get('min_accounts', 0)} - {agreement.get('max_accounts', 0)}", body_style))

        min_total = agreement.get('min_accounts', 0) * agreement.get('rate_per_account', 0)
        max_total = agreement.get('max_accounts', 0) * agreement.get('rate_per_account', 0)
        story.append(Paragraph(f"<b>Monthly Range:</b> ${min_total:.2f} - ${max_total:.2f}", body_style))
        story.append(Spacer(1, 0.3*inch))

        story.append(Paragraph("This agreement confirms the terms and conditions for credit repair outsourcing services as described above.", body_style))
        story.append(Spacer(1, 0.5*inch))

        # Add signature if signed
        if sign_request.get("status") == "signed" and sign_request.get("signature_data"):
            story.append(Paragraph("<b>ELECTRONICALLY SIGNED</b>", bold_style))
            story.append(Spacer(1, 0.1*inch))

            sig_data = sign_request["signature_data"]
            if sig_data.startswith("data:image"):
                sig_data = sig_data.split(",", 1)[1]

            try:
                sig_bytes = base64.b64decode(sig_data)
                sig_io = io.BytesIO(sig_bytes)
                sig_img = RLImage(sig_io, width=2.5*inch, height=1*inch)
                story.append(sig_img)
            except Exception:
                story.append(Paragraph("[Signature on file]", body_style))

            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph(f"<b>Signed by:</b> {sign_request.get('signer_name', '')}", body_style))
            story.append(Paragraph(f"<b>Date:</b> {sign_request.get('signed_at', '')}", body_style))
            story.append(Paragraph(f"<b>IP Address:</b> {sign_request.get('signer_ip', '')}", body_style))
        else:
            story.append(Paragraph("[AWAITING SIGNATURE]", bold_style))

        doc.build(story)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=agreement_{agreement.get('id', 'unknown')[:8]}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")
