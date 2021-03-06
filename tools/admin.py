# -*- coding: utf-8 -*-
import os
import sys
import argparse
from datetime import datetime
from pprint import pprint

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
PROJ_PATH = os.path.dirname(CUR_PATH)

sys.path.append(PROJ_PATH)

from montage.rdb import (make_rdb_session,
                         UserDAO,
                         OrganizerDAO,
                         MaintainerDAO,
                         CoordinatorDAO,
                         reassign_rating_tasks,
                         lookup_user)

from montage.utils import get_threshold_map

GIST_URL = 'https://gist.githubusercontent.com/slaporte/7433943491098d770a8e9c41252e5424/raw/ca394147a841ea5f238502ffd07cbba54b9b1a6a/wlm2015_fr_500.csv'
RANKING_MAX = 40


def warn(msg, force=False):
    if not force:
        confirmed = raw_input('??  %s. Type yes to confirm: ' % msg)

        if not confirmed == 'yes':
            print '-- you typed %r, aborting' % confirmed
            sys.exit(0)

    return


def rdb_console(maint_dao):
    import montage.rdb
    for m in dir(montage.rdb):
        locals()[m] = getattr(montage.rdb, m)

    session = maint_dao.rdb_session

    print 'rdb console:'
    print '  Use session.query() to interact with the db.'
    print '  Commit modifications with session.commit().\n'

    import pdb;pdb.set_trace()

    return


def create_round(user, campaign_id, advance=False, debug=False):
    coord_dao = CoordinatorDAO.from_campaign(user, campaign_id)
    rnd_name = raw_input('?? Round name: ')
    if not rnd_name:
        print '-- round name required, aborting'
        sys.exit(0)
    juror_names_str = raw_input('?? Juror names (comma separated): ')
    juror_names = [j.strip() for j in juror_names_str.split(',')]
    vote_method = raw_input('?? Vote method (rating, yesno, or ranking): ')
    if vote_method not in ['rating', 'yesno', 'ranking']:
        print '-- vote method must be rating, yesno, or ranking, aborting'
        sys.exit(0)
    if vote_method != 'ranking':
        quorum = raw_input('?? Voting quorum: ')
    else:
        quorum = len(juror_names)
    deadline_date_str = raw_input('?? Deadline date: ')
    deadline_date = datetime.strptime(deadline_date_str, '%Y-%m-%d')
    description = raw_input('?? Description: ')
    directions = raw_input('?? Directions: ')
    if not advance:
        category_name = raw_input('?? Category: ')
    rnd = coord_dao.create_round(name=rnd_name,
                                 quorum=quorum,
                                 vote_method=vote_method,
                                 deadline_date=deadline_date,
                                 jurors=juror_names,
                                 directions=directions,
                                 description=description)

    pprint(rnd.to_info_dict())
    print ('++ round %s (%r) created in campaign %s'
           % (rnd.id, rnd.name, campaign_id))

    if not advance:
        entries = coord_dao.add_entries_from_cat(rnd.id, category_name)
        source = category_name
        #entries = maint_dao.add_entries_from_csv_gist(rnd, GIST_URL)
        #source = GIST_URL
        print ('++ prepared %s entries from %r' %
               (len(entries), source))
        coord_dao.add_round_entries(rnd.id, entries)
    else:
        final_rnds = [r for r in campaign.rounds if r.status == 'finalized']
        last_successful_rnd = final_rnds[-1]
        advancing_group = coord_dao.get_rating_advancing_group(last_successful_rnd)
        entries = advancing_group
        if vote_method == 'ranking' and len(entries) > RANKING_MAX:
            print ('-- %s is too many entries for ranking round, aborting'
                   % len(entries))
            # TODO: does not actually roll back the round, since
            # create_round commits on its own. Should individual dao methods
            # have an option to not commit?
            rdb_session.rollback()
            sys.exit(0)

        source = 'round(#%s)' % last_successful_rnd.id
        coord_dao.add_round_entries(rnd.id, advancing_group, source)
    print ('++ added entries from %s to round %s (%r)'
           % (source, rnd.id, rnd.name))

    if debug:
        import pdb;pdb.set_trace()
    return rnd


def edit_quorum(maint_dao, rnd_id, debug):
    rnd = maint_dao.get_round(rnd_id)
    old_quorum = rnd.quorum
    if rnd.status != 'paused':
        print ('-- round must be paused to edit quorum, aborting')
        return
    print ('!! new quorum cannot be lower than current qourum: %s' % old_quorum)
    print ('!! new quorum cannot be higher than the number of jurors: %s' % len(rnd.jurors))
    new_quorum = int(raw_input('?? New quorum: '))
    new_juror_stats = maint_dao.modify_quorum(rnd, new_quorum)

    maint_dao.rdb_session.commit()

    print ('++ changed quorum in round %s (%s) from %s (old quorum) to %s (new quorum)'
           % (rnd.id, rnd.name, old_quorum, new_quorum))
    print ('++ reassigned %s tasks, with mean load of %s tasks per juror'
           % (new_juror_stats['reassigned_task_count'], new_juror_stats['task_count_mean']))

    if debug:
        import pdb;pdb.set_trace()

    return new_juror_stats



def add_organizer(maint_dao, new_org_name, debug=False):
    org_user = maint_dao.add_organizer(new_org_name)

    print '++ added %s as organizer' % new_org_name

    if debug:
        import pdb; pdb.set_trace()
    return


def cancel_campaign(maint_dao, camp_id, debug, force=False):
    campaign = maint_dao.get_campaign(camp_id)
    msg = ('this will cancel campaign %s (%r) and %s rounds, including tasks.'
           % (camp_id, campaign.name, len(campaign.rounds)))

    warn(msg, force)

    maint_dao.cancel_campaign(campaign)

    print ('++ cancelled campaign %s (%r) and %s rounds'
           % (camp_id, campaign.name, len(campaign.rounds)))
    pass


def cancel_round(maint_dao, rnd_id, debug, force=False):
    rnd = maint_dao.get_round(rnd_id)
    msg = ('this will cancel round %s (%r) and its tasks'
           % (rnd_id, rnd.name))

    warn(msg, force)

    ret = maint_dao.cancel_round(rnd)
    stats = rnd.get_count_map()

    print ('++ cancelled round %s (%r), with %s tasks'
           % (rnd.id, rnd.name, stats['total_cancelled_tasks']))

    if debug:
        import pdb;pdb.set_trace()
    return


def activate_round(maint_dao, rnd_id, debug):
    rnd = maint_dao.get_round(rnd_id)

    maint_dao.activate_round(rnd)
    maint_dao.rdb_session.commit()

    print '++ activated round %s (%s)' % (rnd.id, rnd.name)

    if debug:
        import pdb;pdb.set_trace()
    return rnd


def pause_round(maint_dao, rnd_id, debug):
    rnd = maint_dao.get_round(rnd_id)

    maint_dao.pause_round(rnd)
    maint_dao.rdb_session.commit()

    print '++ paused round %s (%r)' % (rnd.id, rnd.name)

    if debug:
        import pdb;pdb.set_trace()
    return rnd


def add_coordinator(maint_dao, camp_id, username, debug):
    camp = maint_dao.get_campaign(camp_id)

    maint_dao.add_coordinator(camp, username=username)

    print ('++ added %r as coordinator for campaign %s (%r)'
           % (username, camp_id, camp.name))
    if debug:
        import pdb;pdb.set_trace()
    return


def remove_coordinator(maint_dao, camp_id, username, debug):
    # TODO: the campaign_coords table should have an is_active column
    raise NotImplementedError('cannot remove coordinators for now')
    '''
    camp = maint_dao.get_campaign(camp_id)
    user = maint_dao.get_or_create_user(username, 'coordinator',
                                        campaign=camp)
    print ('-- remvoed %s as coordinator from campaign %s (%s)'
           % (username, camp_id, camp.name))
    if debug:
        import pdb;pdb.set_trace()
    return
    '''


def check_dupes(user_dao, rnd_id, debug=False):
    dupe_tasks_query = '''
    SELECT users.username, ratings.value, tasks.id, entries.name
    FROM tasks
    JOIN ratings
    ON tasks.id = ratings.task_id
    JOIN round_entries
    ON tasks.round_entry_id = round_entries.id
    JOIN entries
    ON round_entries.entry_id = entries.id
    JOIN users
    ON tasks.user_id = users.id
    WHERE round_entries.round_id = :rnd_id
    AND round_entries.dq_user_id IS NULL'''

    dupe_ratings_query = '''
    SELECT users.username, ratings.value, entries.name
    FROM ratings
    JOIN round_entries
    ON ratings.round_entry_id = round_entries.id
    JOIN entries
    ON round_entries.entry_id = entries.id
    JOIN users
    ON ratings.user_id = users.id
    WHERE round_entries.round_id = :rnd_id
    AND round_entries.dq_user_id IS NULL'''

    dupe_tasks = user_dao.rdb_session.execute(dupe_tasks_query,
                                              {'rnd_id': rnd_id}).fetchall()
    dupe_ratings = user_dao.rdb_session.execute(dupe_ratings_query,
                                                {'rnd_id': rnd_id}).fetchall()

    if len(dupe_tasks) - len(dupe_ratings):
        print ('-- found %s double-assigned tasks'
               % len(dupe_tasks))

    if dupe_ratings:
        print ('-- found %s double-assigned ratings'
               % len(dupe_ratings))

    if debug:
        import pdb;pdb.set_trace()

    return


def retask_duplicate_ratings(maint_dao, rnd_id, debug=False):
    # TODO: does not write to the db yet; session.commit() not called
    import random
    from collections import defaultdict
    from sqlalchemy.orm import joinedload
    from montage.rdb import User, Rating, Round, RoundJuror, Task, RoundEntry

    print 'scanning round %s for duplicate tasks and juror eligibility' % rnd_id

    session = maint_dao.rdb_session
    rnd = session.query(Round).get(rnd_id)

    cur_jurors = session.query(User)\
                        .join(RoundJuror)\
                        .filter_by(round=rnd, is_active=True)\
                        .all()

    cur_tasks = session.query(Task)\
                       .filter_by(cancel_date=None)\
                       .options(joinedload('round_entry'))\
                       .join(RoundEntry)\
                       .filter_by(round=rnd,
                                  dq_user_id=None)\
                       .all()

    elig_map = defaultdict(lambda: list(cur_jurors))
    dup_map = defaultdict(list)
    # only complete_date because that indicates that's the only
    # indicator we have that the user has seen the entry
    # comp_tasks = [t for t in cur_tasks if t.complete_date]
    for task in cur_tasks:
        try:
            elig_map[task.round_entry].remove(task.user)
        except ValueError:
            pass
        dup_map[(task.round_entry_id, task.user_id)].append(task)
    dup_items = [(k, v) for k, v in dup_map.items() if len(v) > 1]
    print 'found %s duplicate tasks out of %s tasks total' % (len(dup_items), len(cur_tasks))
    print 'starting retaskification'
    reassign_count = 0
    revert_count = 0
    for _, dup_tasks in dup_items:
        for i, task in enumerate(reversed(dup_tasks)):
            if i == 0:
                continue  # leave the most recent one alone
            reassign_count += 1
            new_j = random.choice(elig_map[task.round_entry])
            print task, 'is being assigned from', task.user, 'to', new_j
            task.user = new_j
            elig_map[task.round_entry].remove(task.user)
            # the following line makes this safer, but slower
            # also note that sqlalchemy doesn't support limit with its delete
            if task.complete_date:
                revert_count += 1
                assert session.query(Rating).filter_by(task_id=task.id).count() == 1
                session.query(Rating).filter_by(task_id=task.id).delete()
                task.complete_date = None

    print ('reassigned %s tasks and reverted %s ratings for round %s'
           % (reassign_count, revert_count, rnd_id))
    if debug:
        print 'precommit debug prompt:'
        import pdb;pdb.set_trace()
    return

def apply_ratings_from_csv(maint_dao, rnd_id, csv_path, debug=False):
    import datetime

    from unicodecsv import DictReader

    from montage.rdb import Round, User, Entry, RoundEntry, Task, Rating

    session = maint_dao.rdb_session

    print 'applying ratings from %s to round #%s' % (csv_path, rnd_id)

    rnd = session.query(Round).get(rnd_id)

    dr = DictReader(open(csv_path, 'rb'))

    usernames = dr.fieldnames[1:]
    username_map = {}
    for username in usernames:
        user = session.query(User).filter_by(username=username).one()
        username_map[username] = user

    now = datetime.datetime.utcnow()

    new_tasks = []
    new_ratings = []
    del_ratings_count = 0

    for orig_entry_dict in dr:
        entry_dict = dict(orig_entry_dict)
        entry_name = entry_dict.pop('entry')
        _, _, entry_name = entry_name.rpartition('File:')
        entry_name = entry_name.strip()
        entry = session.query(Entry).filter_by(name=entry_name).one()
        round_entry = (session.query(RoundEntry)
                       .filter_by(round=rnd, entry=entry)
                       .one())

        old_tasks = (session.query(Task)
                     .filter_by(round_entry=round_entry)
                     .all())
        # cancel old tasks, delete associated ratings
        for t in old_tasks:
            t.complete_date = None
            t.cancel_date = now

            del_count = session.query(Rating).filter_by(task_id=t.id).delete()
            del_ratings_count += del_count

        # create new tasks, apply associated ratings
        for username, rv in entry_dict.items():
            if not rv.strip():
                continue
            rating_val = float(rv)
            user = username_map[username]
            new_task = Task(user=user, round_entry=round_entry)
            new_task.complete_date = now
            new_tasks.append(new_task)
            new_rating = Rating(value=rating_val, user=user, task=new_task,
                                round_entry=round_entry)
            new_ratings.append(new_rating)
            session.add(new_rating)

    print 'deleted %s old tasks, created %s new ratings' % (del_ratings_count,
                                                            len(new_ratings))

    if debug:
        print 'precommit pdb:'
        import pdb;pdb.set_trace()
    session.commit()
    return



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Admin CLI tools for montage')
    parser.add_argument('--add-organizer',
                        help='add an organizer by username',
                        type=str)
    parser.add_argument('--rdb-console',
                        help='drop to a console for interacting with db objects',
                        action='store_true')
    parser.add_argument('--list',
                        help='list all campaigns and rounds',
                        action='store_true')
    parser.add_argument('--cancel-round',
                        help=('set a round as cancelled, cancel related'
                              ' tasks and remove it from the campaign\'s'
                              ' active  rounds'), type=int)
    parser.add_argument('--cancel-campaign',
                        help=('cancel a campaign by id, including all of its'
                              ' rounds and associated tasks'), type=int)
    parser.add_argument('--add-coordinator',
                        help=('add a coordinator by username to a campaign'),
                        type=str)
    #parser.add_argument('--remove-coordinator',
    #                    help=('remove a coordinator by username from a '
    #                          'campaign (not implemented'),
    #                    type=str)
    parser.add_argument('--create-campaign',
                        help=('create a new campaign with a specified coordinator'),
                        action='store_true')
    parser.add_argument('--create-round',
                        help=('create a new round in a specified campaign'),
                        type=int)
    parser.add_argument('--activate-round',
                        help=('activate a specified round to start voting'),
                        type=int)
    parser.add_argument('--pause-round',
                        help=('pause a specified round if you wish to make edits'),
                        type=int)
    parser.add_argument('--advance-round',
                        help=('finalize a specified round and start the next'),
                        type=int)
    parser.add_argument('--check-dupes',
                        help=('check for double-assigned tasks or ratings in a'
                        ' specified round'),
                        type=int)
    parser.add_argument('--reassign',
                        help=('reassign all the rating tasks in a round'),
                        type=int)
    parser.add_argument('--edit-quorum',
                        help=('edit quorum in a round'),
                        type=int)
    parser.add_argument('--retask-duplicate-ratings',
                        help=('reassign all ratings that were duplicated'),
                        type=int)
    parser.add_argument('--threshold-map',
                        help=('get the threshold map (based on average ratings) for a specified round'),
                        type=int)
    parser.add_argument('--apply-ratings',
                        help='apply ratings based on input (eg --csv-file)',
                        type=int)
    parser.add_argument('--ratings-csv-path',
                        help='ratings file (use with --apply-ratings)',
                        type=str)
    parser.add_argument('--import_gist',
                        help='import files from a gist file',
                        type=str)

    parser.add_argument('--campaign', help='campaign id', type=int)
    parser.add_argument('--round', help='round id', type=int)
    parser.add_argument('--force', action='store_true',
                        help='Use with caution when cancelling things')
    parser.add_argument('--debug', action='store_true')

    args = parser.parse_args()

    rdb_session = make_rdb_session(echo=args.debug)

    user = lookup_user(rdb_session, 'Slaporte')
    user_dao = UserDAO(rdb_session, user)
    maint_dao = MaintainerDAO(user_dao)
    org_dao = OrganizerDAO(user_dao)

    force = args.force

    if args.list:
        campaigns = maint_dao.get_all_campaigns()
        pprint([c.to_details_dict() for c in campaigns])

    if args.rdb_console:
        rdb_console(maint_dao)

    # TODO: active users

    if args.add_organizer:
        new_org_name = args.add_organizer
        org_user = maint_dao.add_organizer(new_org_name)
        print '++ added %s as organizer' % new_org_name

    # TODO: Remove organizer

    if args.create_campaign:
        camp_name = raw_input('?? Campaign name: ')
        if not camp_name:
            print '-- campaign name required, aborting'
            sys.exit(0)
        open_date_str = raw_input('?? Open date: ')
        open_date = datetime.strptime(open_date_str, '%Y-%m-%d')
        close_date_str = raw_input('?? Close date: ')
        close_date = datetime.strptime(close_date_str, '%Y-%m-%d')
        campaign = org_dao.create_campaign(name=camp_name,
                                           open_date=open_date,
                                           close_date=close_date,
                                           coords=[user])
        pprint(campaign.to_info_dict())
        print ('++ campaign %s (%r) created with %r as coordinator'
               % (campaign.id, campaign.name, org_dao.user.username))

    if args.cancel_campaign:
        camp_id = args.cancel_campaign
        campaign = user_dao.get_campaign(camp_id)
        msg = ('this will cancel campaign %s, including all rounds and tasks.'
               % (camp_id))
        warn(msg, force)
        org_dao.cancel_campaign(camp_id)
        print ('++ cancelled campaign %s (%r) and %s rounds'
               % (camp_id, campaign.name, len(campaign.rounds)))

    if args.add_coordinator:
        username = args.add_coordinator
        camp_id = args.campaign
        camp = user_dao.get_campaign(camp_id)
        org_dao.add_coordinator(camp_id, username=username)
        print ('++ added %r as coordinator for campaign %s (%r)'
               % (username, camp_id, camp.name))

    # TODO: Remove coordinator

    if args.create_round:
        campaign_id = args.create_round
        create_round(user_dao, campaign_id)

    if args.cancel_round:
        rnd_id = args.cancel_round
        coord_dao = CoordinatorDAO.from_round(user_dao, rnd_id)
        msg = ('this will cancel round %s and its tasks'
               % (rnd_id,))

        warn(msg, force)

        rnd = coord_dao.cancel_round(rnd_id)
        stats = rnd.get_count_map()

        print ('++ cancelled round %s (%s), with %s tasks'
               % (rnd_id, rnd.name, stats['total_cancelled_tasks']))

    if args.activate_round:
        rnd_id = args.activate_round
        coord_dao = CoordinatorDAO.from_round(user_dao, rnd_id)
        coord_dao.activate_round(rnd_id)
        print '++ activated round %s (%s)' % (rnd.id, rnd.name)

    if args.import_gist:
        rnd_id = args.round
        gist_url = args.import_gist
        coord_dao = CoordinatorDAO.from_round(user_dao, rnd_id)
        entries, warnings = coord_dao.add_entries_from_csv(rnd_id, gist_url)
        stats = coord_dao.add_round_entries(rnd_id, entries,
                                            method='gistcsv',
                                            params={'gist_url': gist_url})
        print '++ added entries to round %s: %r' % (rnd_id, stats)

    if args.pause_round:
        rnd_id = args.pause_round
        coord_dao = CoordinatorDAO.from_round(user_dao, rnd_id)
        maint_dao.pause_round(rnd_id)
        print '++ paused round %s (%r)' % (rnd.id, rnd.name)

    if args.edit_quorum:
        rnd_id = args.edit_quorum
        edit_quorum(maint_dao, rnd_id, args.debug)

    if args.advance_round:
        rnd_id = args.advance_round
        coord_dao = CoordinatorDAO.from_round(user_dao, rnd_id)
        avg_ratings_map = coord_dao.get_round_average_rating_map(rnd_id)
        threshold_map = get_threshold_map(avg_ratings_map)
        print '-- Round threshold map...'
        pprint(threshold_map)
        threshold = raw_input('?? Include at least how many images: ')
        threshold = int(threshold)
        if not threshold:
            print '-- no threshold provided, aborting'
            sys.exit(0)
        cur_thresh = [t for t, c in sorted(threshold_map.items()) \
                      if c >= threshold][-1]
        coord_dao.finalize_rating_round(rnd_id, cur_thresh)
        camp_id = coord_dao.campaign.id
        print ('++ ready to import %s entries to the next round in campaign %s...'
               % (threshold_map[cur_thresh], camp_id))
        next_round = create_round(user_dao, camp_id, advance=True, debug=debug)

    if args.check_dupes:
        rnd_id = args.check_dupes
        check_dupes(maint_dao, rnd_id, args.debug)

    if args.reassign:
        rnd_id = args.reassign
        coord_dao = CoordinatorDAO.from_round(user_dao, rnd_id)
        rnd = coord_dao.get_round(rnd_id)
        new_jurors = rnd.jurors
        stats = reassign_rating_tasks(user_dao.rdb_session,
                                      rnd, new_jurors,
                                      reassign_all=True)
        print '++ reassignment stats: '
        pprint(stats)

    if args.retask_duplicate_ratings:
        rnd_id = args.retask_duplicate_ratings
        retask_duplicate_ratings(maint_dao, rnd_id, args.debug)
        # TODO

    if args.threshold_map:
        rnd_id = args.threshold_map
        cood_dao = CoordinatorDAO.from_round(user_dao, rnd_id)
        avg_ratings_map = coord_dao.get_round_average_rating_map(rnd_id)
        thresh_map = get_threshold_map(avg_ratings_map)
        print ('-- Round threshold map for round %s (%r) ...'
               % (rnd.id, rnd.name))
        pprint(thresh_map)

    if args.apply_ratings:
        rnd_id = args.apply_ratings
        csv_path = args.ratings_csv_path
        apply_ratings_from_csv(maint_dao, rnd_id, csv_path, debug=args.debug)


    rdb_session.commit()

    # TODO: move out rdb_session commit/rollback in a try finally
    # rdb_session.commit()

    #if args.remove_coordinator:
    #    username = args.remove_coordinator
    #    camp_id = args.campaign
    #    remove_coordinator(maint_dao, camp_id, username, args.debug)
