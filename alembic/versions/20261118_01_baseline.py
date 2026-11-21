"""Baseline of the existing BrowserStrategy schema."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('achievements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('icon_url', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_achievements_id'), 'achievements', ['id'], unique=False)
    op.create_table('battles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=8), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('state', sa.JSON(), nullable=False),
        sa.Column('winner_side', sa.Integer(), nullable=True),
        sa.Column('rewarded', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_battles_status'), 'battles', ['status'], unique=False)
    op.create_table('enemies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('level', sa.Integer(), nullable=True),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('hp', sa.Integer(), nullable=True),
        sa.Column('melee_attack', sa.Integer(), nullable=True),
        sa.Column('physical_defense', sa.Integer(), nullable=True),
        sa.Column('magic_power', sa.Integer(), nullable=True),
        sa.Column('magic_resistance', sa.Integer(), nullable=True),
        sa.Column('ranged_attack', sa.Integer(), nullable=True),
        sa.Column('agility', sa.Integer(), nullable=True),
        sa.Column('mind', sa.Integer(), nullable=True),
        sa.Column('bonus_melee_damage', sa.Integer(), nullable=True),
        sa.Column('bonus_ranged_damage', sa.Integer(), nullable=True),
        sa.Column('bonus_magic_damage', sa.Integer(), nullable=True),
        sa.Column('bonus_melee_defense', sa.Integer(), nullable=True),
        sa.Column('bonus_ranged_defense', sa.Integer(), nullable=True),
        sa.Column('bonus_magic_defense', sa.Integer(), nullable=True),
        sa.Column('exp_reward', sa.Integer(), nullable=True),
        sa.Column('gold_reward', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_enemies_id'), 'enemies', ['id'], unique=False)
    op.create_table('enterprises',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('sector', sa.String(), nullable=True),
        sa.Column('resource_type', sa.String(), nullable=True),
        sa.Column('resource_stored', sa.Integer(), nullable=True),
        sa.Column('area', sa.Integer(), nullable=True),
        sa.Column('last_production_time', sa.DateTime(), nullable=True),
        sa.Column('workers_count', sa.Integer(), nullable=True),
        sa.Column('max_workers', sa.Integer(), nullable=True),
        sa.Column('max_storage', sa.Integer(), nullable=True),
        sa.Column('salary', sa.Integer(), nullable=True),
        sa.Column('item_price', sa.Integer(), nullable=True),
        sa.Column('balance', sa.Integer(), nullable=True),
        sa.Column('storage_multiplier', sa.Integer(), nullable=True),
        sa.Column('production_type', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_enterprises_id'), 'enterprises', ['id'], unique=False)
    op.create_index(op.f('ix_enterprises_name'), 'enterprises', ['name'], unique=False)
    op.create_table('quest_scenarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('min_level', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quest_scenarios_id'), 'quest_scenarios', ['id'], unique=False)
    op.create_table('unit_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('fraction', sa.String(), nullable=True),
        sa.Column('level_required', sa.Integer(), nullable=True),
        sa.Column('max_quantity', sa.Integer(), nullable=True),
        sa.Column('icon_url', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_unit_types_id'), 'unit_types', ['id'], unique=False)
    op.create_index(op.f('ix_unit_types_name'), 'unit_types', ['name'], unique=False)
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('password', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('fraction', sa.String(), nullable=True),
        sa.Column('pending_attribute_points', sa.Integer(), nullable=True),
        sa.Column('stamina', sa.Integer(), nullable=True),
        sa.Column('energy', sa.Integer(), nullable=True),
        sa.Column('agility', sa.Integer(), nullable=True),
        sa.Column('mind', sa.Integer(), nullable=True),
        sa.Column('melee_attack', sa.Integer(), nullable=True),
        sa.Column('ranged_attack', sa.Integer(), nullable=True),
        sa.Column('magic_power', sa.Integer(), nullable=True),
        sa.Column('physical_defense', sa.Integer(), nullable=True),
        sa.Column('magic_resistance', sa.Integer(), nullable=True),
        sa.Column('bonus_melee_damage', sa.Integer(), nullable=True),
        sa.Column('bonus_ranged_damage', sa.Integer(), nullable=True),
        sa.Column('bonus_magic_damage', sa.Integer(), nullable=True),
        sa.Column('bonus_melee_defense', sa.Integer(), nullable=True),
        sa.Column('bonus_ranged_defense', sa.Integer(), nullable=True),
        sa.Column('bonus_magic_defense', sa.Integer(), nullable=True),
        sa.Column('experience', sa.Integer(), nullable=True),
        sa.Column('level', sa.Integer(), nullable=True),
        sa.Column('gold', sa.Integer(), nullable=True),
        sa.Column('wood', sa.Integer(), nullable=True),
        sa.Column('stone', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('map_sector', sa.String(), nullable=True),
        sa.Column('map_x', sa.Integer(), nullable=True),
        sa.Column('map_y', sa.Integer(), nullable=True),
        sa.Column('workplace', sa.String(), nullable=True),
        sa.Column('last_salary_time', sa.DateTime(), nullable=True),
        sa.Column('last_quit_time', sa.DateTime(), nullable=True),
        sa.Column('daily_work_minutes', sa.Integer(), nullable=True),
        sa.Column('last_work_day', sa.DateTime(), nullable=True),
        sa.Column('work_start_time', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('army_slots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('unit_key', sa.String(length=32), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'slot')
    )
    op.create_index(op.f('ix_army_slots_user_id'), 'army_slots', ['user_id'], unique=False)
    op.create_table('battle_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('battle_id', sa.Integer(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('side', sa.Integer(), nullable=False),
        sa.Column('action', sa.JSON(), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('battle_id', 'seq')
    )
    op.create_index(op.f('ix_battle_actions_battle_id'), 'battle_actions', ['battle_id'], unique=False)
    op.create_table('battle_histories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('completion_time', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_battle_histories_id'), 'battle_histories', ['id'], unique=False)
    op.create_table('battle_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('battle_id', sa.Integer(), nullable=False),
        sa.Column('side', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('battle_id', 'side')
    )
    op.create_index(op.f('ix_battle_participants_battle_id'), 'battle_participants', ['battle_id'], unique=False)
    op.create_index(op.f('ix_battle_participants_user_id'), 'battle_participants', ['user_id'], unique=False)
    op.create_table('battle_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('enemy_id', sa.Integer(), nullable=True),
        sa.Column('player_position', sa.JSON(), nullable=True),
        sa.Column('enemy_position', sa.JSON(), nullable=True),
        sa.Column('player_hp', sa.Integer(), nullable=True),
        sa.Column('enemy_hp', sa.Integer(), nullable=True),
        sa.Column('turn', sa.Integer(), nullable=True),
        sa.Column('player_moves', sa.Integer(), nullable=True),
        sa.Column('enemy_moves', sa.Integer(), nullable=True),
        sa.Column('battle_ended', sa.Boolean(), nullable=True),
        sa.Column('winner', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['enemy_id'], ['enemies.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_battle_state_id'), 'battle_state', ['id'], unique=False)
    op.create_table('items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('item_type', sa.String(), nullable=True),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('stats', sa.JSON(), nullable=True),
        sa.Column('is_equipped', sa.Boolean(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('durability', sa.Integer(), nullable=True),
        sa.Column('max_durability', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_items_id'), 'items', ['id'], unique=False)
    op.create_table('player_ratings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('wins', sa.Integer(), nullable=True),
        sa.Column('losses', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_player_ratings_id'), 'player_ratings', ['id'], unique=False)
    op.create_table('tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scenario_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('level_required', sa.Integer(), nullable=True),
        sa.Column('order_in_scenario', sa.Integer(), nullable=True),
        sa.Column('reward_gold', sa.Integer(), nullable=True),
        sa.Column('reward_wood', sa.Integer(), nullable=True),
        sa.Column('reward_stone', sa.Integer(), nullable=True),
        sa.Column('reward_exp', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['scenario_id'], ['quest_scenarios.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_id'), 'tasks', ['id'], unique=False)
    op.create_table('user_achievements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('achievement_id', sa.Integer(), nullable=True),
        sa.Column('obtained_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['achievement_id'], ['achievements.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_achievements_id'), 'user_achievements', ['id'], unique=False)
    op.create_table('user_units',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('unit_type_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['unit_type_id'], ['unit_types.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_units_id'), 'user_units', ['id'], unique=False)
    op.create_table('battle_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('battle_id', sa.Integer(), nullable=True),
        sa.Column('turn', sa.Integer(), nullable=True),
        sa.Column('player_action', sa.String(), nullable=True),
        sa.Column('player_hp', sa.Integer(), nullable=True),
        sa.Column('enemy_hp', sa.Integer(), nullable=True),
        sa.Column('player_damage', sa.Integer(), nullable=True),
        sa.Column('enemy_damage', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['battle_id'], ['battle_state.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_battle_logs_id'), 'battle_logs', ['id'], unique=False)
    op.create_table('equipped_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('helmet_id', sa.Integer(), nullable=True),
        sa.Column('armor_id', sa.Integer(), nullable=True),
        sa.Column('boots_id', sa.Integer(), nullable=True),
        sa.Column('right_hand_id', sa.Integer(), nullable=True),
        sa.Column('left_hand_id', sa.Integer(), nullable=True),
        sa.Column('back_id', sa.Integer(), nullable=True),
        sa.Column('jewelry_1_id', sa.Integer(), nullable=True),
        sa.Column('jewelry_2_id', sa.Integer(), nullable=True),
        sa.Column('jewelry_3_id', sa.Integer(), nullable=True),
        sa.Column('jewelry_4_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['armor_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['back_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['boots_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['helmet_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['jewelry_1_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['jewelry_2_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['jewelry_3_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['jewelry_4_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['left_hand_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['right_hand_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_equipped_items_id'), 'equipped_items', ['id'], unique=False)
    op.create_table('shop_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_template_id', sa.Integer(), nullable=True),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('level_required', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['item_template_id'], ['items.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shop_items_id'), 'shop_items', ['id'], unique=False)
    op.create_table('user_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_tasks_id'), 'user_tasks', ['id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_tasks_id'), table_name='user_tasks')
    op.drop_table('user_tasks')
    op.drop_index(op.f('ix_shop_items_id'), table_name='shop_items')
    op.drop_table('shop_items')
    op.drop_index(op.f('ix_equipped_items_id'), table_name='equipped_items')
    op.drop_table('equipped_items')
    op.drop_index(op.f('ix_battle_logs_id'), table_name='battle_logs')
    op.drop_table('battle_logs')
    op.drop_index(op.f('ix_user_units_id'), table_name='user_units')
    op.drop_table('user_units')
    op.drop_index(op.f('ix_user_achievements_id'), table_name='user_achievements')
    op.drop_table('user_achievements')
    op.drop_index(op.f('ix_tasks_id'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index(op.f('ix_player_ratings_id'), table_name='player_ratings')
    op.drop_table('player_ratings')
    op.drop_index(op.f('ix_items_id'), table_name='items')
    op.drop_table('items')
    op.drop_index(op.f('ix_battle_state_id'), table_name='battle_state')
    op.drop_table('battle_state')
    op.drop_index(op.f('ix_battle_participants_user_id'), table_name='battle_participants')
    op.drop_index(op.f('ix_battle_participants_battle_id'), table_name='battle_participants')
    op.drop_table('battle_participants')
    op.drop_index(op.f('ix_battle_histories_id'), table_name='battle_histories')
    op.drop_table('battle_histories')
    op.drop_index(op.f('ix_battle_actions_battle_id'), table_name='battle_actions')
    op.drop_table('battle_actions')
    op.drop_index(op.f('ix_army_slots_user_id'), table_name='army_slots')
    op.drop_table('army_slots')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_unit_types_name'), table_name='unit_types')
    op.drop_index(op.f('ix_unit_types_id'), table_name='unit_types')
    op.drop_table('unit_types')
    op.drop_index(op.f('ix_quest_scenarios_id'), table_name='quest_scenarios')
    op.drop_table('quest_scenarios')
    op.drop_index(op.f('ix_enterprises_name'), table_name='enterprises')
    op.drop_index(op.f('ix_enterprises_id'), table_name='enterprises')
    op.drop_table('enterprises')
    op.drop_index(op.f('ix_enemies_id'), table_name='enemies')
    op.drop_table('enemies')
    op.drop_index(op.f('ix_battles_status'), table_name='battles')
    op.drop_table('battles')
    op.drop_index(op.f('ix_achievements_id'), table_name='achievements')
    op.drop_table('achievements')
