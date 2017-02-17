"""empty message

Revision ID: 36abd98c57e5
Revises: 23a7fc516054
Create Date: 2017-02-11 16:28:07.204329

"""

# revision identifiers, used by Alembic.
revision = '36abd98c57e5'
down_revision = '23a7fc516054'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('ccvote',
    sa.Column('ccvoteID', sa.Integer(), nullable=False),
    sa.Column('voterID', sa.Integer(), nullable=True),
    sa.Column('lmvoteID', sa.Integer(), nullable=True),
    sa.Column('fcvoteID', sa.Integer(), nullable=True),
    sa.Column('time', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['fcvoteID'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['lmvoteID'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['voterID'], ['characters.id'], ),
    sa.PrimaryKeyConstraint('ccvoteID')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('ccvote')
    # ### end Alembic commands ###
