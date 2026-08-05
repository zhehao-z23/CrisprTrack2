function test_spt_track_global_gap_memory
% Regression tests for the v5 trackMem-aware global-gap boundary.

test_dir = fileparts(mfilename('fullpath'));
repo_root = fileparts(test_dir);
addpath(fullfile(repo_root, 'trajectory_extraction', 'pipeline', 'matlab_deps'));

sptpara.mtl = 2;
sptpara.max_disp = 1;

% One globally empty frame separates two three-detection pieces. With
% trackMem=0, v5 must preserve the v4 split behavior and neither piece is
% long enough to pass the unchanged segment eligibility rule.
one_missing_frame = [10.0, 10.0, 1; ...
                     10.1, 10.0, 2; ...
                     10.2, 10.0, 3; ...
                     10.3, 10.0, 5; ...
                     10.4, 10.0, 6; ...
                     10.5, 10.0, 7];
sptpara.trackMem = 0;
[trajlist, traj] = spt_track(sptpara, one_missing_frame);
assert(isempty(trajlist));
assert(isempty(traj));

% The same detections must form one trajectory when the single globally
% missing frame is within trackMem.
sptpara.trackMem = 1;
[trajlist, traj] = spt_track(sptpara, one_missing_frame);
assert(~isempty(trajlist));
assert(numel(traj) == 1);
assert(traj(1).length == 5);
assert(isequal(traj(1).pos(:,3), [1; 2; 3; 5; 6; 7]));

% A two-frame global gap remains a hard boundary for trackMem=1.
two_missing_frames = one_missing_frame;
two_missing_frames(4:6,3) = [6; 7; 8];
sptpara.trackMem = 1;
[trajlist, traj] = spt_track(sptpara, two_missing_frames);
assert(isempty(trajlist));
assert(isempty(traj));

% Raising memory to exactly the observed gap permits the same continuous
% candidate under the unchanged fixed max_disp model.
sptpara.trackMem = 2;
[trajlist, traj] = spt_track(sptpara, two_missing_frames);
assert(~isempty(trajlist));
assert(numel(traj) == 1);
assert(traj(1).length == 5);
assert(isequal(traj(1).pos(:,3), [1; 2; 3; 6; 7; 8]));

% The production default is trackMem=3. Verify both sides of that exact
% boundary rather than relying only on smaller synthetic memory values.
three_missing_frames = one_missing_frame;
three_missing_frames(4:6,3) = [7; 8; 9];
sptpara.trackMem = 2;
[trajlist, traj] = spt_track(sptpara, three_missing_frames);
assert(isempty(trajlist));
assert(isempty(traj));

sptpara.trackMem = 3;
[trajlist, traj] = spt_track(sptpara, three_missing_frames);
assert(~isempty(trajlist));
assert(numel(traj) == 1);
assert(traj(1).length == 5);
assert(isequal(traj(1).pos(:,3), [1; 2; 3; 7; 8; 9]));

% Two well-separated particles must remain two identities when both cross a
% permitted global gap. This guards against a length gain created by a
% trivial cross-particle swap.
competition = [10.0, 10.0, 1; 20.0, 20.0, 1; ...
               10.1, 10.0, 2; 19.9, 20.0, 2; ...
               10.2, 10.0, 4; 19.8, 20.0, 4; ...
               10.3, 10.0, 5; 19.7, 20.0, 5];
sptpara.trackMem = 1;
[trajlist, traj] = spt_track(sptpara, competition);
assert(~isempty(trajlist));
assert(numel(traj) == 2);
mean_x = sort(arrayfun(@(item) mean(item.pos(:,1)), traj));
assert(mean_x(1) < 12);
assert(mean_x(2) > 18);
for index = 1:numel(traj)
    assert(traj(index).length == 3);
    assert(isequal(traj(index).pos(:,3), [1; 2; 4; 5]));
end

% An allowed gap and a disallowed gap can coexist in one detection table.
% The allowed gaps must be retained inside each block, while the large gap
% must still produce two separately numbered trajectories.
mixed_gaps = [10.0, 10.0, 1; ...
              10.1, 10.0, 2; ...
              10.2, 10.0, 4; ...
              10.3, 10.0, 5; ...
              20.0, 20.0, 10; ...
              20.1, 20.0, 11; ...
              20.2, 20.0, 13; ...
              20.3, 20.0, 14];
sptpara.trackMem = 1;
[trajlist, traj] = spt_track(sptpara, mixed_gaps);
assert(~isempty(trajlist));
assert(numel(traj) == 2);
frame_sets = {traj(1).pos(:,3), traj(2).pos(:,3)};
assert(isequal(frame_sets{1}, [1; 2; 4; 5]));
assert(isequal(frame_sets{2}, [10; 11; 13; 14]));
assert(isequal(unique(trajlist(:,4)), [1; 2]));

fprintf('SPT_GLOBAL_GAP_MEMORY_REGRESSION_OK\n');
end
