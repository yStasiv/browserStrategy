/* Playback and live animation consume the same recorded events. */
const BattleEvents = (() => {
    const labels = {
        UNIT_MOVED: 'move', UNIT_ATTACKED: 'attack', COUNTERATTACK: 'retaliation',
        UNIT_DEFENDED: 'defend', UNIT_WAITED: 'wait', UNIT_SKIPPED: 'skip',
        SIDE_SURRENDERED: 'surrender', BATTLE_FINISHED: 'battle_end',
        ELEMENTAL_SUMMONED: 'summon',
        HERO_ATTACKED: 'hero_attack',
        LUCK_ROLLED: 'luck', MORALE_ROLLED: 'morale', UNIT_HEALED: 'heal',
    };

    function logEvent(event) {
        return labels[event.type] ? {...event.payload, type: labels[event.type]} : null;
    }

    function apply(state, event) {
        if (event.type === 'UNIT_MOVED') {
            const [x, y] = event.payload.to;
            Object.assign(state.stacks[event.actor_id], {x, y});
        } else if (event.type === 'LUCK_ROLLED' || event.type === 'MORALE_ROLLED') {
            const stack = state.stacks[event.actor_id];
            const counter = event.type === 'LUCK_ROLLED' ? 'luck_streak' : 'morale_streak';
            if (event.payload.streak_after === 1) delete stack[counter];
            else stack[counter] = event.payload.streak_after;
            if (event.type === 'MORALE_ROLLED') stack.ready = event.payload.next_ready_at;
        } else if (event.type === 'UNIT_HEALED') {
            const stack = state.stacks[event.target_id] ??= structuredClone(event.payload.stack_after);
            Object.assign(stack, {count: event.payload.target_count_after, top_hp: event.payload.top_hp});
        } else if (event.type === 'DAMAGE_APPLIED') {
            Object.assign(state.stacks[event.target_id], {
                count: event.payload.creatures_after, top_hp: event.payload.top_hp,
            });
        } else if (['STATUS_APPLIED', 'STATUS_EXPIRED'].includes(event.type) && event.payload.effect === 'defend') {
            state.stacks[event.target_id].defending = event.type === 'STATUS_APPLIED';
        } else if (event.type === 'UNIT_KILLED') {
            delete state.stacks[event.target_id];
        }
        if (event.changes) {
            Object.assign(state, event.changes.fields);
            Object.assign(state.stacks, structuredClone(event.changes.stacks));
            for (const id of event.changes.removed_stacks) delete state.stacks[id];
        }
    }

    function animate(event, stackElements, state, cellSize, speed) {
        const element = stackElements[event.actor_id];
        if (!element || !element.animate || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        const actor = state.stacks[event.actor_id];
        if (!actor) return;
        if (event.type === 'UNIT_MOVED') {
            const path = [event.payload.from, ...event.payload.path];
            return element.animate(path.map(([x, y]) => ({
                transform: `translate(${(x - actor.x) * cellSize}px, ${(y - actor.y) * cellSize}px)`,
            })), {duration: Math.min(600, 110 * (path.length - 1)) / speed});
        }
        if (['UNIT_ATTACKED', 'COUNTERATTACK'].includes(event.type)) {
            const target = state.stacks[event.target_id];
            if (!target) return;
            const length = event.payload.ranged ? -4 : 12;
            const offset = `translate(${Math.sign(target.x - actor.x) * length}px, ${Math.sign(target.y - actor.y) * length}px)`;
            return element.animate([
                {transform: 'translate(0, 0)'}, {transform: offset}, {transform: 'translate(0, 0)'},
            ], {duration: 160 / speed});
        }
    }
    function damageTracker(partial, heroes = {}) {
        const sides = [new Map(), new Map()];
        const heroTotals = new Map(Object.values(heroes).map(hero => [hero.owner, 0]));
        return {
            apply(event) {
                const heroHit = event.hero_damage;
                if (heroHit) {
                    heroTotals.set(heroHit.side, (heroTotals.get(heroHit.side) ?? 0) + heroHit.amount);
                }
                const hit = event.creature_damage;
                if (!hit) return;
                const creatures = sides[hit.side];
                creatures.set(hit.unit, (creatures.get(hit.unit) || 0) + hit.amount);
            },
            summary() {
                return {partial, sides: sides.map((units, side) => {
                    const creatures = [...units].map(([unit, amount]) => ({unit, amount}));
                    creatures.sort((a, b) => b.amount - a.amount);
                    return {
                        side, creatures, hero_total: heroTotals.get(side) ?? null,
                        total: creatures.reduce((sum, unit) => sum + unit.amount, 0),
                    };
                })};
            },
        };
    }

    function replayQueue(state, turns, cursor, limit = 50) {
        if (state.status !== 'active' || !state.active_id) return [];
        const queue = [{id: state.active_id}];
        for (const turn of turns) {
            if (queue.length >= limit) break;
            if (turn.index >= cursor) queue.push({id: turn.id});
        }
        return queue;
    }

    return {apply, animate, logEvent, damageTracker, replayQueue};
})();
