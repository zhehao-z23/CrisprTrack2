function test_v42_v5_spt_batch_gap_control
% Same synthetic TIFF through v4.2 and v5 to isolate the global-gap change.

test_dir = fileparts(mfilename('fullpath'));
v5_root = fileparts(test_dir);
code_root = fileparts(v5_root);
v42_root = fullfile(code_root, 'OligoLiveFish-ML-ZZH-v4.2-candidate-qc');
assert(isfolder(v42_root), 'Sibling v4.2 control source is required locally.');

scratch = tempname;
mkdir(scratch);
cleanup = onCleanup(@() rmdir(scratch, 's')); %#ok<NASGU>
tif_path = fullfile(scratch, 'synthetic_v42_v5_gap_control.tif');
v42_output = fullfile(scratch, 'v42');
v5_output = fullfile(scratch, 'v5');
mkdir(v42_output);
mkdir(v5_output);

image_size = 64;
[xx, yy] = meshgrid(1:image_size, 1:image_size);
detection_frames = [1, 2, 3, 5, 6, 7];
for frame_index = 1:7
    frame = ones(image_size, image_size, 'single') * 100;
    if ismember(frame_index, detection_frames)
        gaussian = 5000 * exp( ...
            -((xx - (31 + 0.15 * frame_index)).^2 ...
              + (yy - (33 + 0.10 * frame_index)).^2) / (2 * 1.4^2) ...
        );
        frame = frame + gaussian;
    end
    frame = uint16(round(frame));
    if frame_index == 1
        imwrite(frame, tif_path, 'tif', 'Compression', 'none');
    else
        imwrite( ...
            frame, tif_path, 'tif', ...
            'WriteMode', 'append', 'Compression', 'none' ...
        );
    end
end

v42_pipeline = fullfile(v42_root, 'trajectory_extraction', 'pipeline');
v42_deps = fullfile(v42_pipeline, 'matlab_deps');
v5_pipeline = fullfile(v5_root, 'trajectory_extraction', 'pipeline');
v5_deps = fullfile(v5_pipeline, 'matlab_deps');

addpath(v42_deps, '-begin');
addpath(v42_pipeline, '-begin');
clear spt_batch spt_track
spt_batch(tif_path, 1.0, 0.1, v42_output, false, 2.0);
v42_result = load( ...
    fullfile(v42_output, 'synthetic_v42_v5_gap_control.mat') ...
);
assert(isempty(v42_result.traj));
rmpath(v42_pipeline);
rmpath(v42_deps);

addpath(v5_deps, '-begin');
addpath(v5_pipeline, '-begin');
clear spt_batch spt_track
spt_batch(tif_path, 1.0, 0.1, v5_output, false, 2.0);
v5_result = load( ...
    fullfile(v5_output, 'synthetic_v42_v5_gap_control.mat') ...
);
assert(numel(v5_result.traj) == 1);
assert(v5_result.traj(1).length == 5);
assert(isequal(v5_result.traj(1).pos(:,3), detection_frames'));

fprintf('V42_V5_SPT_BATCH_GAP_CONTROL_OK\n');
end
