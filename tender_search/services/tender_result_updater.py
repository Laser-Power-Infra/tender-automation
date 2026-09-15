import logging
import re

logger = logging.getLogger(__name__)


def _cr_to_number(val: str | None) -> str:
    if not val:
        return ""
    s = str(val).strip()
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*cr", s, re.I)
    if m:
        num = m.group(1).replace(",", "")
        try:
            return str(int(float(num) * 1e7))
        except ValueError:
            return num
    return re.sub(r"[^0-9.]", "", s)


def update_tender_result(reference_no: str, l1: str, contract_amount: str, competitors: str | None = None, current_status: str | None = None) -> dict:
    # ponytail: reusable DB sync — view runs via sync_to_async thread, so sync ORM direct
    from tender_search.models import TenderMerged  # type: ignore

    parts = re.split(r"<br\s*/?>", reference_no, flags=re.I)
    ref = parts[0].strip()
    has_ra = len(parts) > 1 and parts[1].strip() != ""
    amt_num = _cr_to_number(contract_amount)
    is_laser = "laser power" in (l1 or "").lower()

    def _find(r: str):
        m = TenderMerged.objects.filter(referenceno__iexact=r, apm="YES", participated=True).first()  # type: ignore
        if m is None:
            m = TenderMerged.objects.filter(referenceno__icontains=r.strip(), apm="YES", participated=True).first()  # type: ignore
        return m

    merged = _find(ref)

    if merged is None:
        logger.info("[TenderResultUpdater] skip %s not in TenderMerged", ref)
        print(f"[TenderResultUpdater] skip {ref} not in TenderMerged")
        return {"referenceNo": ref, "found": False, "skipped": "not_found", "has_ra": has_ra}

    old_l1 = (merged.nameofrank1 or "").strip().lower()  # type: ignore
    if old_l1 == (l1 or "").strip().lower():
        logger.info("[TenderResultUpdater] skip %s L1 unchanged (%r)", ref, l1)
        print(f"[TenderResultUpdater] skip {ref} L1 unchanged ({l1!r})")
        return {"referenceNo": ref, "found": True, "skipped": "l1_unchanged"}

    def _do_save(m, laser: bool, _l1: str, _amt: str, _has_ra: bool, _cur: str | None):
        old_status = (m.currentstatus or "").strip().upper()  # type: ignore
        if _cur and _cur.strip():
            new_status = _cur.strip()
        else:
            new_status = old_status if old_status in ("AWARDED", "CANCELLED") else "FINANCIAL EVALUATION"
        if laser:
            m.nameofrank1 = _l1  # type: ignore
            m.valueofrank1 = _amt  # type: ignore
            m.ourrank = "1"  # type: ignore
            m.ourvalue = _amt  # type: ignore
            m.currentstatus = new_status  # type: ignore
        else:
            m.nameofrank1 = _l1  # type: ignore
            m.valueofrank1 = _amt  # type: ignore
            m.ourrank = None  # type: ignore
            m.ourvalue = None  # type: ignore
            m.currentstatus = new_status  # type: ignore
        if _has_ra:
            m.reverseauctionapplicable = True  # type: ignore
        m.save()
        return new_status

    new_status = _do_save(merged, is_laser, l1.strip(), amt_num, has_ra, current_status)
    if competitors:
        logger.info("[TenderResultUpdater] competitors %s -> %r", ref, competitors)
        print(f"[TenderResultUpdater] competitors {ref} -> {competitors!r}")
    if is_laser:
        logger.info("[TenderResultUpdater] updated %s -> nameOfRank1=%r valueOfRank1=%r ourRank=1 ourValue=%r currentStatus=%s reverseAuctionApplicable=%s competitors=%r", ref, l1, amt_num, amt_num, new_status, has_ra, competitors)
        print(f"[TenderResultUpdater] updated {ref} -> nameOfRank1={l1!r} valueOfRank1={amt_num!r} ourRank=1 ourValue={amt_num!r} currentStatus={new_status} reverseAuctionApplicable={has_ra} competitors={competitors!r}")
    else:
        logger.info("[TenderResultUpdater] updated %s -> nameOfRank1=%r valueOfRank1=%r ourRank=None currentStatus=%s reverseAuctionApplicable=%s competitors=%r", ref, l1, amt_num, new_status, has_ra, competitors)
        print(f"[TenderResultUpdater] updated {ref} -> nameOfRank1={l1!r} valueOfRank1={amt_num!r} ourRank=None currentStatus={new_status} reverseAuctionApplicable={has_ra} competitors={competitors!r}")

    return {
        "referenceNo": ref,
        "found": True,
        "updated": True,
        "nameOfRank1": l1.strip(),
        "valueOfRank1": amt_num,
        "ourRank": "1" if is_laser else None,
        "ourValue": amt_num if is_laser else None,
        "currentStatus": new_status,
        "is_laser": is_laser,
        "has_ra": has_ra,
        "reverseAuctionApplicable": has_ra,
        "competitors": competitors,
    }
