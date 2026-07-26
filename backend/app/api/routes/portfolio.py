from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, get_database
from backend.app.models.portfolio_lot import PortfolioLot
from backend.app.models.user import User
from backend.app.schemas.portfolio import (
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
    PortfolioLotResponse,
    PortfolioResponse,
)
from backend.app.services import portfolio_service
from backend.app.services.portfolio_service import (
    PortfolioAssetNotFoundError,
    PortfolioLotNotFoundError,
    PortfolioPositionLimitError,
)


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _lot_response(lot: PortfolioLot) -> PortfolioLotResponse:
    return PortfolioLotResponse.model_validate(lot, from_attributes=True)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Portfolio resource not found.",
    )


def _position_limit_error(exc: PortfolioPositionLimitError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "portfolio_position_limit_reached",
            "message": (
                f"Free accounts can hold up to "
                f"{exc.position_limit} portfolio positions."
            ),
            "position_limit": exc.position_limit,
            "position_count": exc.position_count,
            "upgrade_url": "/pricing",
        },
    )


@router.get("", response_model=PortfolioResponse)
def read_portfolio(
    db: Session = Depends(get_database),
    current_user: User = Depends(get_current_user),
) -> PortfolioResponse:
    return portfolio_service.get_portfolio(db, current_user)


@router.post(
    "/lots",
    response_model=PortfolioLotResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_portfolio_lot(
    payload: PortfolioLotCreateRequest,
    db: Session = Depends(get_database),
    current_user: User = Depends(get_current_user),
) -> PortfolioLotResponse:
    try:
        lot = portfolio_service.create_portfolio_lot(db, current_user, payload)
        db.commit()
    except PortfolioPositionLimitError as exc:
        db.rollback()
        raise _position_limit_error(exc) from exc
    except (PortfolioAssetNotFoundError, PortfolioLotNotFoundError) as exc:
        db.rollback()
        raise _not_found() from exc
    except Exception:
        db.rollback()
        raise
    return _lot_response(lot)


@router.patch("/lots/{lot_id}", response_model=PortfolioLotResponse)
def update_portfolio_lot(
    lot_id: UUID,
    payload: PortfolioLotPatchRequest,
    db: Session = Depends(get_database),
    current_user: User = Depends(get_current_user),
) -> PortfolioLotResponse:
    try:
        lot = portfolio_service.update_portfolio_lot(
            db,
            current_user,
            lot_id,
            payload,
        )
        db.commit()
    except PortfolioPositionLimitError as exc:
        db.rollback()
        raise _position_limit_error(exc) from exc
    except (PortfolioAssetNotFoundError, PortfolioLotNotFoundError) as exc:
        db.rollback()
        raise _not_found() from exc
    except Exception:
        db.rollback()
        raise
    return _lot_response(lot)


@router.delete("/lots/{lot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio_lot(
    lot_id: UUID,
    db: Session = Depends(get_database),
    current_user: User = Depends(get_current_user),
) -> Response:
    try:
        portfolio_service.delete_portfolio_lot(db, current_user, lot_id)
        db.commit()
    except PortfolioPositionLimitError as exc:
        db.rollback()
        raise _position_limit_error(exc) from exc
    except (PortfolioAssetNotFoundError, PortfolioLotNotFoundError) as exc:
        db.rollback()
        raise _not_found() from exc
    except Exception:
        db.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
