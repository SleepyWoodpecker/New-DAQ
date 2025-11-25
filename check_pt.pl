my $prev_hv_pkt_cnt = -1;
my $prev_lv_pkt_cnt = -1;

while (<>) {
    chomp;
    
    # 1. Split the line by comma into an array of fields
    #    The fields are now in @fields
    my @fields = split(/,/, $_);
    
    # 2. Use negative array indices to get the values:
    #    $fields[-3] is the 3rd-to-last element.
    #    $fields[-1] is the last element.
    my $cur_hv = int $fields[-3]; # Third-to-last value (292688 in your example)
    my $cur_lv = int $fields[-1]; # Last value (146041 in your example)

    printf("$.: bad %d -> %d\n", $prev, $cur) if (
        $prev_hv_pkt_cnt >= 0 && $cur_hv - $prev_hv_pkt_cnt != 1 ||
        $prev_lv_pkt_cnt >= 0 && $cur_lv - $prev_lv_pkt_cnt != 1
    );
    
    $prev_hv_pkt_cnt = $cur_hv;
    $prev_lv_pkt_cnt = $cur_lv;
}