"""Add name-based Trello list discovery for the mebel module

Ikki ustun qo'shadi, boshqa hech narsaga tegmaydi:
  - app_settings.mebel_trello_board_id  -> qaysi doska kuzatiladi
  - departments.trello_list_keywords    -> ro'yxatlar NOMIGA qarab qaysi
                                            bo'limga tegishli ekani

Qo'lda yozilgan (autogenerate EMAS): avtogeneratsiya bu bazada bog'liq
bo'lmagan "drift"ni ham tortib kelgan edi — `financial_suggestions` jadvalini
tashlash, 4 ta app_settings ustunini o'chirish, enum turlarini almashtirish va
`uq_task_claims_one_pending` indeksini yo'q qilish (bu indeks bitta vazifaga
bitta PENDING claim cheklovini ta'minlaydi, uni tushirib yuborish haqiqiy
regressiya bo'lardi). Shu sabab faqat kerakli ikki ustun qo'lda yozildi.

Revision ID: b4e17c9a2d31
Revises: 77a6fe7328cd
"""

from alembic import op
import sqlalchemy as sa

revision = "b4e17c9a2d31"
down_revision = "77a6fe7328cd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("mebel_trello_board_id", sa.String(length=50), nullable=True))
    op.add_column("app_settings", sa.Column("mebel_ingest_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("departments", sa.Column("trello_list_keywords", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("departments", "trello_list_keywords")
    op.drop_column("app_settings", "mebel_ingest_start_at")
    op.drop_column("app_settings", "mebel_trello_board_id")
